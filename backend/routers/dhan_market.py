"""
Dhan Market Data Router - centralized proxy endpoints for Dhan v2 APIs.

The design is cache-first and shared across users so backend fetches are reused.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Literal, Optional, Union
import asyncio
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import time
from urllib.parse import urlencode

import httpx
import websockets
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from routers.auth import get_current_user
from models import User
from utils.market_utils import IST, get_latest_market_date, is_market_holiday
from services.redis_store import (
    cache_get_json,
    cache_set_json,
    close_pubsub,
    create_pubsub,
    is_rate_limited,
    ping_redis,
    publish_json,
)

router = APIRouter()

DHAN_BASE_URL = "https://api.dhan.co/v2"
RATE_LIMIT_PER_MINUTE = int(os.getenv("DHAN_RATE_LIMIT_PER_MINUTE", "60"))
STREAM_CHANNEL_PREFIX = os.getenv("MARKET_STREAM_CHANNEL_PREFIX", "market").strip() or "market"


def _cache_ttls() -> dict:
    return {
        "quote": int(os.getenv("DHAN_CACHE_TTL_QUOTE", "3")),
        "options": int(os.getenv("DHAN_CACHE_TTL_OPTIONS", "3")),
        "history": int(os.getenv("DHAN_CACHE_TTL_HISTORY", "60")),
        "chart_tick": int(os.getenv("DHAN_CACHE_TTL_CHART_TICK", "1")),
    }


DEFAULT_CHART_SYMBOL_MAP = {
    "NIFTY": "13",
    "BANKNIFTY": "25",
    "FINNIFTY": "27",
    "MIDCPNIFTY": "442",
}

CHART_TIMEFRAME_TO_INTERVAL = {
    "1": 1,
    "5": 5,
    "15": 15,
    "25": 25,
    "60": 60,
}

CHART_DAILY_TIMEFRAME = "D"

CHART_LOOKBACK_CANDLES = {
    "1": 300,
    "5": 240,
    "15": 200,
    "25": 180,
    "60": 160,
}

CHART_DAILY_FROM_DATE = os.getenv("DHAN_CHART_DAILY_FROM_DATE", "2000-01-01")

# Dhan serves at most 90 days of intraday candles per request, and retains
# roughly 5 years of intraday history. Daily candles have no such span limit.
CHART_INTRADAY_MAX_SPAN_DAYS = int(os.getenv("DHAN_CHART_INTRADAY_MAX_SPAN_DAYS", "90"))
CHART_INTRADAY_MAX_HISTORY_DAYS = int(os.getenv("DHAN_CHART_INTRADAY_MAX_HISTORY_DAYS", str(365 * 5)))
# How many trading days back the bootstrap will search for a session that
# actually has candles, so a closed market still renders a chart.
CHART_SESSION_LOOKBACK_DAYS = int(os.getenv("DHAN_CHART_SESSION_LOOKBACK_DAYS", "7"))

CHART_DEFAULT_EXCHANGE_SEGMENT = os.getenv("DHAN_CHART_DEFAULT_EXCHANGE_SEGMENT", "IDX_I")
CHART_DEFAULT_INSTRUMENT = os.getenv("DHAN_CHART_DEFAULT_INSTRUMENT", "INDEX")
CHART_LAST_TICK_TTL = int(os.getenv("DHAN_CHART_LAST_TICK_TTL", "180"))
DHAN_FULL_DEPTH_20_WS_URL = os.getenv("DHAN_FULL_DEPTH_20_WS_URL", "wss://depth-api-feed.dhan.co/twentydepth")
DHAN_FULL_DEPTH_200_WS_URL = os.getenv("DHAN_FULL_DEPTH_200_WS_URL", "wss://full-depth-api.dhan.co/twohundreddepth")
DHAN_FULL_DEPTH_TIMEOUT_SEC = float(os.getenv("DHAN_FULL_DEPTH_TIMEOUT_SEC", "8"))

# --- Dhan Live Market Feed (real-time binary tick stream) ---
# Streaming ticks replaces REST-polling /marketfeed/ltp, which added ~1-2s of
# latency per sample on top of the provider's own delay.
DHAN_LIVE_FEED_WS_URL = os.getenv("DHAN_LIVE_FEED_WS_URL", "wss://api-feed.dhan.co")
# Subscribe request codes.
DHAN_FEED_REQUEST_TICKER = 15
DHAN_FEED_REQUEST_DISCONNECT = 12
# Feed response codes (first byte of every packet).
DHAN_FEED_CODE_TICKER = 2
DHAN_FEED_CODE_QUOTE = 4
DHAN_FEED_CODE_PREV_CLOSE = 6
DHAN_FEED_CODE_DISCONNECT = 50
# Fixed packet sizes per response code, used to split frames that carry
# multiple packets. Deterministic, so we don't depend on the header length
# field being payload-inclusive or not.
DHAN_FEED_PACKET_SIZES = {
    DHAN_FEED_CODE_TICKER: 16,
    DHAN_FEED_CODE_QUOTE: 50,
    5: 12,                       # OI packet
    DHAN_FEED_CODE_PREV_CLOSE: 16,
    8: 162,                      # Full packet (quote + 5 depth levels)
    DHAN_FEED_CODE_DISCONNECT: 10,
}
DHAN_FEED_CONNECT_TIMEOUT_SEC = float(os.getenv("DHAN_FEED_CONNECT_TIMEOUT_SEC", "10"))
DHAN_FEED_IDLE_TIMEOUT_SEC = float(os.getenv("DHAN_FEED_IDLE_TIMEOUT_SEC", "45"))
ISIN_PATTERN = re.compile(r"^IN[A-Z0-9]{10}$", re.IGNORECASE)
DHAN_SCRIP_MASTER_URL = os.getenv("DHAN_SCRIP_MASTER_URL", "https://images.dhan.co/api-data/api-scrip-master.csv")
DHAN_SCRIP_MASTER_TIMEOUT = float(os.getenv("DHAN_SCRIP_MASTER_TIMEOUT", "25"))
DHAN_SCRIP_MASTER_TTL_SEC = int(os.getenv("DHAN_SCRIP_MASTER_TTL_SEC", "21600"))
_DHAN_SCRIP_MASTER_LOCAL_PATH = Path(
    os.getenv(
        "DHAN_SCRIP_MASTER_LOCAL_PATH",
        str(Path(tempfile.gettempdir()) / "stocksage" / "dhan_api_scrip_master.csv"),
    )
)

_chart_symbol_map_cache: Dict[str, Dict[str, str]] = {}
_chart_symbol_map_cache_loaded_at = 0.0
_chart_symbol_map_lock = asyncio.Lock()
_chart_last_tick_memory: Dict[str, Dict[str, Union[int, float]]] = {}


def _get_dhan_headers() -> Dict[str, str]:
    access_token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()

    if not access_token or not client_id:
        raise HTTPException(
            status_code=500,
            detail="Market data credentials are not configured. Set DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID.",
        )

    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "access-token": access_token,
        "client-id": client_id,
    }


async def _dhan_post(endpoint: str, payload: dict) -> dict:
    url = f"{DHAN_BASE_URL}{endpoint}"
    headers = _get_dhan_headers()

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = "Dhan API request failed"
        try:
            body = exc.response.json()
            if isinstance(body, dict) and body.get("remarks"):
                detail = str(body.get("remarks"))
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=detail)
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Unable to reach the market data service")


def _cache_key(prefix: str, endpoint: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{endpoint}|{canonical}".encode()).hexdigest()
    return f"dhan:{prefix}:{digest}"


async def _cached_dhan_post(endpoint: str, payload: dict, bucket: str) -> dict:
    ttl = max(1, _cache_ttls().get(bucket, 3))
    key = _cache_key(bucket, endpoint, payload)

    cached = await cache_get_json(key)
    if cached is not None:
        return {"source": "cache", "data": cached}

    global_limit_key = f"dhan:rl:{bucket}"
    if await is_rate_limited(global_limit_key, RATE_LIMIT_PER_MINUTE, 60):
        raise HTTPException(status_code=429, detail="Rate limit reached for market data. Please retry shortly.")

    live = await _dhan_post(endpoint, payload)
    await cache_set_json(key, live, ttl)
    await publish_json(
        f"{STREAM_CHANNEL_PREFIX}:{bucket}",
        {
            "bucket": bucket,
            "endpoint": endpoint,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": live,
        },
    )
    return {"source": "live", "data": live}


class SecuritiesRequest(BaseModel):
    securities: Dict[str, List[Union[int, str]]] = Field(
        ...,
        example={"NSE_EQ": [1333], "NSE_FNO": [49081, 49082]},
    )


class HistoricalDailyRequest(BaseModel):
    securityId: Union[int, str]
    exchangeSegment: str
    instrument: str
    fromDate: str
    toDate: str
    expiryCode: int = 0
    oi: bool = False


class HistoricalIntradayRequest(BaseModel):
    securityId: Union[int, str]
    exchangeSegment: str
    instrument: str
    interval: int = 1
    fromDate: str
    toDate: str
    oi: bool = False


class OptionChainRequest(BaseModel):
    UnderlyingScrip: int
    UnderlyingSeg: str
    Expiry: str


class ExpiryListRequest(BaseModel):
    UnderlyingScrip: int
    UnderlyingSeg: str


class ExpiredOptionsRequest(BaseModel):
    exchangeSegment: str
    interval: int = 1
    securityId: Union[int, str]
    instrument: str
    expiryFlag: str
    expiryCode: int
    strike: str
    drvOptionType: str
    requiredData: List[str]
    fromDate: str
    toDate: str


class CacheWarmJob(BaseModel):
    bucket: Literal["quote", "options", "history"]
    endpoint: str
    payload: dict


class CacheWarmRequest(BaseModel):
    jobs: List[CacheWarmJob] = Field(default_factory=list)


class StreamPublishRequest(BaseModel):
    bucket: Literal["quote", "options", "history", "broadcast"]
    event: str = "market_update"
    data: dict
    symbol: Optional[str] = None


ALLOWED_WARM_ENDPOINTS = {
    "quote": {"/marketfeed/ltp", "/marketfeed/ohlc", "/marketfeed/quote"},
    "options": {"/optionchain", "/optionchain/expirylist"},
    "history": {"/charts/historical", "/charts/intraday", "/charts/rollingoption"},
}


def _stream_channel(bucket: str) -> str:
    return f"{STREAM_CHANNEL_PREFIX}:{bucket}"


def _chart_symbol_map() -> Dict[str, str]:
    mapping = dict(DEFAULT_CHART_SYMBOL_MAP)
    raw = os.getenv("DHAN_SYMBOL_SECURITY_MAP", "").strip()
    if not raw:
        return mapping

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            for key, value in parsed.items():
                k = str(key).strip().upper()
                v = str(value).strip()
                if k and v:
                    mapping[k] = v
    except Exception:
        return mapping

    return mapping


def _normalize_symbol_key(value: str) -> str:
    return str(value or "").strip().upper()


def _safe_row_value(row: dict, key: str) -> str:
    return str(row.get(key) or "").strip()


def _build_symbols_from_scrip_master(csv_content: str) -> Dict[str, Dict[str, str]]:
    parsed_map: Dict[str, Dict[str, str]] = {}
    reader = csv.DictReader(csv_content.splitlines())

    for row in reader:
        exch = _safe_row_value(row, "SEM_EXM_EXCH_ID").upper()
        segment = _safe_row_value(row, "SEM_SEGMENT").upper()
        security_id = _safe_row_value(row, "SEM_SMST_SECURITY_ID")
        if exch != "NSE" or segment != "E" or not security_id:
            continue

        symbol_name = _safe_row_value(row, "SM_SYMBOL_NAME")
        trading_symbol = _safe_row_value(row, "SEM_TRADING_SYMBOL")
        instrument_name = _safe_row_value(row, "SEM_INSTRUMENT_NAME").upper() or "EQUITY"

        identity = {
            "securityId": security_id,
            "exchangeSegment": "NSE_EQ",
            "instrument": instrument_name,
        }

        symbol_key = _normalize_symbol_key(symbol_name)
        if symbol_key:
            parsed_map[symbol_key] = identity

        trading_key = _normalize_symbol_key(trading_symbol)
        if trading_key:
            parsed_map[trading_key] = identity
            if "-" in trading_key:
                base = _normalize_symbol_key(trading_key.split("-", 1)[0])
                if base:
                    parsed_map.setdefault(base, identity)

    return parsed_map


async def _load_scrip_master_text() -> str:
    try:
        async with httpx.AsyncClient(timeout=DHAN_SCRIP_MASTER_TIMEOUT) as client:
            resp = await client.get(DHAN_SCRIP_MASTER_URL)
            resp.raise_for_status()
            text = resp.text
            _DHAN_SCRIP_MASTER_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
            _DHAN_SCRIP_MASTER_LOCAL_PATH.write_text(text, encoding="utf-8")
            return text
    except Exception:
        if _DHAN_SCRIP_MASTER_LOCAL_PATH.exists():
            return _DHAN_SCRIP_MASTER_LOCAL_PATH.read_text(encoding="utf-8")
        raise


async def _ensure_chart_symbol_map_cache() -> Dict[str, Dict[str, str]]:
    global _chart_symbol_map_cache, _chart_symbol_map_cache_loaded_at

    now = time.time()
    if _chart_symbol_map_cache and (now - _chart_symbol_map_cache_loaded_at) < max(300, DHAN_SCRIP_MASTER_TTL_SEC):
        return _chart_symbol_map_cache

    async with _chart_symbol_map_lock:
        now = time.time()
        if _chart_symbol_map_cache and (now - _chart_symbol_map_cache_loaded_at) < max(300, DHAN_SCRIP_MASTER_TTL_SEC):
            return _chart_symbol_map_cache

        csv_text = await _load_scrip_master_text()
        _chart_symbol_map_cache = _build_symbols_from_scrip_master(csv_text)
        _chart_symbol_map_cache_loaded_at = time.time()

    return _chart_symbol_map_cache


async def _resolve_chart_identity(
    symbol: str,
    security_id: Optional[str],
    exchange_segment: Optional[str],
    instrument: Optional[str],
) -> Dict[str, str]:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")

    env_symbol_map = _chart_symbol_map()
    resolved_security_id = (security_id or "").strip()
    resolved_exchange = (exchange_segment or "").strip()
    resolved_instrument = (instrument or "").strip()

    # Dhan expects its own numeric securityId; ISIN values should be auto-resolved by symbol.
    if resolved_security_id and ISIN_PATTERN.match(resolved_security_id):
        resolved_security_id = ""

    if not resolved_security_id and normalized_symbol in env_symbol_map:
        resolved_security_id = env_symbol_map[normalized_symbol]

    if not resolved_security_id:
        try:
            scrip_map = await _ensure_chart_symbol_map_cache()
            matched = scrip_map.get(normalized_symbol)
            if matched:
                resolved_security_id = matched.get("securityId", "")
                resolved_exchange = resolved_exchange or matched.get("exchangeSegment", "")
                resolved_instrument = resolved_instrument or matched.get("instrument", "")
        except Exception:
            # Soft-fail and fall back to existing behavior when scrip-master is unavailable.
            pass

    if not resolved_security_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Security ID is required for this symbol. Pass `securityId` or set DHAN_SYMBOL_SECURITY_MAP"
            ),
        )

    resolved_exchange = resolved_exchange or CHART_DEFAULT_EXCHANGE_SEGMENT
    resolved_instrument = resolved_instrument or CHART_DEFAULT_INSTRUMENT

    return {
        "symbol": normalized_symbol,
        "securityId": resolved_security_id,
        "exchangeSegment": resolved_exchange,
        "instrument": resolved_instrument,
    }


def _resolve_timeframe(timeframe: str) -> int:
    tf = str(timeframe).strip()
    if tf not in CHART_TIMEFRAME_TO_INTERVAL:
        allowed = ", ".join(sorted(CHART_TIMEFRAME_TO_INTERVAL.keys(), key=int))
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe. Allowed: {allowed}")
    return CHART_TIMEFRAME_TO_INTERVAL[tf]


def _intraday_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _date_only(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def _floor_datetime_to_interval(value: datetime, interval_min: int) -> datetime:
    """Normalize datetime to interval bucket so chart bootstrap cache keys are stable."""
    if interval_min <= 1:
        return value.replace(second=0, microsecond=0)

    total_minutes = value.hour * 60 + value.minute
    floored_total_minutes = (total_minutes // interval_min) * interval_min
    floored_hour = floored_total_minutes // 60
    floored_minute = floored_total_minutes % 60
    return value.replace(hour=floored_hour, minute=floored_minute, second=0, microsecond=0)


def _get_intraday_session_day(now_ist: datetime) -> date:
    """Resolve the trading day for intraday charts (today on trading days, else previous market day)."""
    current_day = now_ist.date()
    # Before market open (09:15 IST), intraday candles for current day are not available yet.
    # Use previous trading day to avoid generating invalid from/to intraday windows.
    if not is_market_holiday(current_day) and now_ist.time() >= datetime(
        now_ist.year,
        now_ist.month,
        now_ist.day,
        9,
        15,
        tzinfo=IST,
    ).time():
        return current_day

    temp_day = current_day - timedelta(days=1)
    for _ in range(15):
        if not is_market_holiday(temp_day):
            return temp_day
        temp_day -= timedelta(days=1)

    return temp_day


def _previous_trading_day(day: date) -> date:
    """Walk back to the closest earlier day the NSE was open."""
    temp_day = day - timedelta(days=1)
    for _ in range(15):
        if not is_market_holiday(temp_day):
            return temp_day
        temp_day -= timedelta(days=1)
    return temp_day


def _parse_chart_date(value: str, field: str) -> date:
    """Parse a YYYY-MM-DD query param into a date, or raise a 400."""
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be a valid date in YYYY-MM-DD format",
        )


def _intraday_chunks(
    from_dt: datetime,
    to_dt: datetime,
    max_span_days: int = CHART_INTRADAY_MAX_SPAN_DAYS,
) -> list[tuple[datetime, datetime]]:
    """Split a window into <= max_span_days slices to respect Dhan's intraday cap."""
    if from_dt >= to_dt:
        return []

    chunks: list[tuple[datetime, datetime]] = []
    span = timedelta(days=max_span_days)
    cursor = from_dt
    while cursor < to_dt:
        chunk_end = min(cursor + span, to_dt)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end
    return chunks


def _build_intraday_payload(
    identity: Dict[str, str],
    timeframe: str,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
) -> Dict[str, Union[str, int, bool]]:
    interval_min = _resolve_timeframe(timeframe)

    # Explicit window (custom range) bypasses the current-session defaulting.
    if from_dt is not None and to_dt is not None:
        return {
            "securityId": identity["securityId"],
            "exchangeSegment": identity["exchangeSegment"],
            "instrument": identity["instrument"],
            "interval": interval_min,
            "oi": False,
            "fromDate": _intraday_datetime(from_dt),
            "toDate": _intraday_datetime(to_dt),
        }

    now_ist = datetime.now(IST)
    session_day = _get_intraday_session_day(now_ist)
    market_open = datetime(
        session_day.year,
        session_day.month,
        session_day.day,
        9,
        15,
        tzinfo=IST,
    )
    market_close = datetime(
        session_day.year,
        session_day.month,
        session_day.day,
        15,
        30,
        tzinfo=IST,
    )

    if now_ist.date() > session_day:
        session_end = market_close
    else:
        session_end = min(now_ist, market_close)

    # Floor to a single minute (not the full interval) so the requested window --
    # and therefore the cache key -- advances every minute. Flooring to
    # interval_min made a 5m chart lag by up to 5 minutes during live trading.
    to_dt = _floor_datetime_to_interval(session_end, 1)
    # Dhan intraday endpoint often behaves like exclusive upper bound; nudge by one interval.
    to_dt = min(market_close + timedelta(minutes=interval_min), to_dt + timedelta(minutes=interval_min))

    # Intraday chart bootstrap should represent the current trading session only.
    from_dt = market_open

    if from_dt >= to_dt:
        from_dt = market_open

    return {
        "securityId": identity["securityId"],
        "exchangeSegment": identity["exchangeSegment"],
        "instrument": identity["instrument"],
        "interval": interval_min,
        "oi": False,
        "fromDate": _intraday_datetime(from_dt),
        "toDate": _intraday_datetime(to_dt),
    }


def _session_window(session_day: date, interval_min: int) -> tuple[datetime, datetime]:
    """Full 09:15-15:30 IST trading window for a given day, as an intraday from/to pair."""
    market_open = datetime(session_day.year, session_day.month, session_day.day, 9, 15, tzinfo=IST)
    market_close = datetime(session_day.year, session_day.month, session_day.day, 15, 30, tzinfo=IST)
    # Dhan treats the upper bound as exclusive; nudge by one interval.
    return market_open, market_close + timedelta(minutes=interval_min)


def _build_daily_historical_payload(
    identity: Dict[str, str],
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> Dict[str, Union[str, int, bool]]:
    if to_date is None:
        to_date = get_latest_market_date(datetime.now(IST))

    from_value = CHART_DAILY_FROM_DATE if from_date is None else _date_only(
        datetime(from_date.year, from_date.month, from_date.day, tzinfo=IST)
    )

    return {
        "securityId": identity["securityId"],
        "exchangeSegment": identity["exchangeSegment"],
        "instrument": identity["instrument"],
        "expiryCode": 0,
        "oi": False,
        "fromDate": from_value,
        "toDate": _date_only(
            datetime(
                to_date.year,
                to_date.month,
                to_date.day,
                tzinfo=IST,
            )
        ),
    }


def _ist_date_from_epoch(epoch: int) -> date:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(IST).date()


def _epoch_for_ist_start_of_day(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=IST).timestamp())


def _session_bucket_epoch(day: date, hour: int, minute: int) -> int:
    return int(datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST).timestamp())


def _fill_intraday_session_gaps(candles: list[dict], timeframe: str) -> list[dict]:
    if not candles:
        return candles

    # Gap-filling is useful for short frames where occasional missing buckets occur,
    # but it can flatten higher intervals like 60m if provider data is sparse.
    if str(timeframe) not in {"1", "5", "15"}:
        return candles

    interval_min = CHART_TIMEFRAME_TO_INTERVAL.get(str(timeframe))
    if not interval_min:
        return candles

    if len(candles) < 2:
        return candles

    first_day = _ist_date_from_epoch(int(candles[0]["time"]))
    last_day = _ist_date_from_epoch(int(candles[-1]["time"]))
    if first_day != last_day:
        return candles

    start_epoch = _session_bucket_epoch(first_day, 9, 15)
    session_close_epoch = _session_bucket_epoch(first_day, 15, 30)
    step = interval_min * 60

    by_time = {int(c["time"]): c for c in candles}
    sorted_times = sorted(by_time.keys())

    # Only fill *interior* gaps, up to the latest real candle — never extrapolate
    # a flat line out to the 15:30 close. During a live session that padding would
    # push the chart's right edge hours into the future, so incoming live ticks
    # land on a buried mid-series candle and the visible candle appears frozen.
    end_epoch = min(session_close_epoch, sorted_times[-1]) if sorted_times else session_close_epoch

    expected_buckets = ((end_epoch - start_epoch) // step) + 1
    if len(by_time) < max(2, expected_buckets // 3):
        return candles

    first_known_time = sorted_times[0] if sorted_times else start_epoch
    first_known_candle = by_time.get(first_known_time)
    prev_close = float(first_known_candle["open"]) if first_known_candle else None

    filled: list[dict] = []
    for t in range(start_epoch, end_epoch + 1, step):
        existing = by_time.get(t)
        if existing:
            prev_close = float(existing["close"])
            filled.append(existing)
            continue

        if prev_close is None:
            continue

        filled.append(
            {
                "time": t,
                "open": round(prev_close, 4),
                "high": round(prev_close, 4),
                "low": round(prev_close, 4),
                "close": round(prev_close, 4),
            }
        )

    return filled if filled else candles


async def _append_current_session_daily_candle(identity: Dict[str, str], candles: list[dict]) -> list[dict]:
    """Append/replace today's daily candle derived from intraday feed so daily chart stays current."""
    intraday_payload = _build_intraday_payload(identity, "5")
    intraday_response = await _cached_dhan_post("/charts/intraday", intraday_payload, "history")
    intraday_candles = _to_lightweight_candles(intraday_response.get("data") or {})
    if not intraday_candles:
        return candles

    session_day = _get_intraday_session_day(datetime.now(IST))
    today_intraday = [c for c in intraday_candles if _ist_date_from_epoch(int(c["time"])) == session_day]
    if not today_intraday:
        return candles

    open_price = float(today_intraday[0]["open"])
    close_price = float(today_intraday[-1]["close"])
    high_price = max(float(c["high"]) for c in today_intraday)
    low_price = min(float(c["low"]) for c in today_intraday)
    day_epoch = _epoch_for_ist_start_of_day(session_day)

    merged = [c for c in candles if _ist_date_from_epoch(int(c["time"])) != session_day]
    merged.append(
        {
            "time": day_epoch,
            "open": round(open_price, 4),
            "high": round(high_price, 4),
            "low": round(low_price, 4),
            "close": round(close_price, 4),
        }
    )
    merged.sort(key=lambda c: int(c["time"]))
    return merged


def _to_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _security_id_for_quote_payload(security_id: str) -> Union[int, str]:
    parsed = _to_int(security_id)
    return parsed if parsed is not None else security_id


def _extract_ltp_and_ts(raw_payload: dict, exchange_segment: str, security_id: str) -> Dict[str, int | float]:
    candidates: list[dict] = []

    if isinstance(raw_payload, dict):
        candidates.append(raw_payload)
        data_value = raw_payload.get("data")
        if isinstance(data_value, dict):
            candidates.append(data_value)

    sec_key_candidates = [security_id, str(security_id), str(security_id).lstrip("0")]

    def _find_payload(node: object) -> Optional[dict]:
        if isinstance(node, dict):
            for sec in sec_key_candidates:
                hit = node.get(sec)
                if isinstance(hit, dict):
                    return hit
                if _to_float(hit) is not None:
                    return {"ltp": hit}

            nested = node.get(exchange_segment)
            if isinstance(nested, dict):
                resolved = _find_payload(nested)
                if resolved:
                    return resolved

            for value in node.values():
                resolved = _find_payload(value)
                if resolved:
                    return resolved

        if isinstance(node, list):
            for value in node:
                resolved = _find_payload(value)
                if resolved:
                    return resolved
        return None

    payload = None
    for candidate in candidates:
        payload = _find_payload(candidate)
        if payload:
            break

    if payload is None:
        raise HTTPException(status_code=502, detail="Unable to parse the market data response for latest price")

    price = None
    for key in ["lastPrice", "last_price", "ltp", "LTP", "price"]:
        price = _to_float(payload.get(key))
        if price is not None:
            break

    if price is None and len(payload) == 1:
        only_value = next(iter(payload.values()))
        price = _to_float(only_value)

    if price is None:
        raise HTTPException(status_code=502, detail="Market data response did not include the latest traded price")

    tick_epoch = None
    for key in ["last_traded_time", "lastTradeTime", "LTT", "timestamp", "time"]:
        tick_epoch = _to_int(payload.get(key))
        if tick_epoch is not None and tick_epoch > 0:
            break

    if tick_epoch is None:
        tick_epoch = int(datetime.now(timezone.utc).timestamp())

    return {
        "price": round(price, 4),
        "timestamp": tick_epoch,
    }


def _extract_quote_security_payload(raw_payload: dict, exchange_segment: str, security_id: str) -> dict:
    candidates: list[dict] = []

    if isinstance(raw_payload, dict):
        candidates.append(raw_payload)
        data_value = raw_payload.get("data")
        if isinstance(data_value, dict):
            candidates.append(data_value)

    sec_key_candidates = [security_id, str(security_id), str(security_id).lstrip("0")]

    def _find_payload(node: object) -> Optional[dict]:
        if isinstance(node, dict):
            for sec in sec_key_candidates:
                hit = node.get(sec)
                if isinstance(hit, dict):
                    return hit

            nested = node.get(exchange_segment)
            if isinstance(nested, dict):
                resolved = _find_payload(nested)
                if resolved:
                    return resolved

            for value in node.values():
                resolved = _find_payload(value)
                if resolved:
                    return resolved

        if isinstance(node, list):
            for value in node:
                resolved = _find_payload(value)
                if resolved:
                    return resolved
        return None

    for candidate in candidates:
        payload = _find_payload(candidate)
        if payload:
            return payload

    raise HTTPException(status_code=502, detail="Unable to parse the market data response for market depth")


def _normalize_depth_side(side_payload: object, limit: int) -> list[dict]:
    rows: list[dict] = []
    if not isinstance(side_payload, list):
        return rows

    for row in side_payload:
        if not isinstance(row, dict):
            continue

        price = None
        for key in ["price", "Price", "bid_price", "ask_price", "rate"]:
            price = _to_float(row.get(key))
            if price is not None:
                break

        quantity = None
        for key in ["quantity", "qty", "Quantity", "volume", "bid_qty", "ask_qty"]:
            quantity = _to_int(row.get(key))
            if quantity is not None:
                break

        orders = None
        for key in ["orders", "order_count", "Orders", "num_orders"]:
            orders = _to_int(row.get(key))
            if orders is not None:
                break

        if price is None:
            continue

        rows.append(
            {
                "price": round(price, 4),
                "quantity": int(quantity or 0),
                "orders": int(orders or 0),
            }
        )

        if len(rows) >= limit:
            break

    return rows


def _extract_depth_from_quote(raw_payload: dict, exchange_segment: str, security_id: str, limit: int) -> dict:
    payload = _extract_quote_security_payload(raw_payload, exchange_segment, security_id)

    depth = payload.get("depth") if isinstance(payload.get("depth"), dict) else None
    market_depth = payload.get("marketDepth") if isinstance(payload.get("marketDepth"), dict) else None

    buy_side_candidates = [
        depth.get("buy") if depth else None,
        depth.get("bids") if depth else None,
        market_depth.get("buy") if market_depth else None,
        market_depth.get("bids") if market_depth else None,
        payload.get("buyDepth"),
        payload.get("buy"),
        payload.get("bids"),
    ]
    sell_side_candidates = [
        depth.get("sell") if depth else None,
        depth.get("offers") if depth else None,
        depth.get("asks") if depth else None,
        market_depth.get("sell") if market_depth else None,
        market_depth.get("offers") if market_depth else None,
        market_depth.get("asks") if market_depth else None,
        payload.get("sellDepth"),
        payload.get("sell"),
        payload.get("offers"),
        payload.get("asks"),
    ]

    buy_rows: list[dict] = []
    for candidate in buy_side_candidates:
        buy_rows = _normalize_depth_side(candidate, limit)
        if buy_rows:
            break

    sell_rows: list[dict] = []
    for candidate in sell_side_candidates:
        sell_rows = _normalize_depth_side(candidate, limit)
        if sell_rows:
            break

    if not buy_rows and not sell_rows:
        raise HTTPException(status_code=502, detail="Market data response did not include market depth rows")

    return {
        "buy": buy_rows,
        "sell": sell_rows,
    }


def _build_dhan_feed_ws_url() -> str:
    """Connection URL for Dhan's live market feed."""
    access_token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()

    if not access_token or not client_id:
        raise HTTPException(
            status_code=500,
            detail="Market data credentials are not configured. Set DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID.",
        )

    query = urlencode(
        {
            "version": 2,
            "token": access_token,
            "clientId": client_id,
            "authType": 2,
        }
    )
    return f"{DHAN_LIVE_FEED_WS_URL}?{query}"


def _build_feed_subscribe_payload(identity: Dict[str, str]) -> dict:
    """Ticker subscription - LTP + last-trade-time only, the lightest packet."""
    return {
        "RequestCode": DHAN_FEED_REQUEST_TICKER,
        "InstrumentCount": 1,
        "InstrumentList": [
            {
                "ExchangeSegment": identity["exchangeSegment"],
                "SecurityId": str(identity["securityId"]),
            }
        ],
    }


def _split_feed_packets(frame: bytes) -> list[bytes]:
    """A single frame can carry several packets back to back."""
    packets: list[bytes] = []
    offset = 0
    n = len(frame)

    while offset + 8 <= n:
        code = frame[offset]
        size = DHAN_FEED_PACKET_SIZES.get(code)

        if size is None:
            # Unknown code: fall back to the header's length field.
            msg_len = int.from_bytes(frame[offset + 1:offset + 3], "little", signed=False)
            size = msg_len if 8 <= msg_len <= (n - offset) else 0

        if size <= 0 or offset + size > n:
            break

        packets.append(frame[offset:offset + size])
        offset += size

    return packets


# Dhan's live feed sends Last-Trade-Time as seconds-since-epoch expressed in IST,
# i.e. it is already shifted +5:30 relative to a true UTC epoch. Our candle series
# (bootstrap/history) uses true UTC epochs, so we subtract this to line the live
# ticks up with the candle grid; otherwise every tick lands 5.5h in the future and
# the client rejects it as "too far ahead", freezing the chart.
IST_OFFSET_SECONDS = 5 * 3600 + 30 * 60  # 19800


def _parse_ticker_packet(packet: bytes) -> Optional[Dict[str, Union[int, float]]]:
    """Ticker packet: header(8) + LTP float32 + last-trade-time int32, little endian."""
    if len(packet) < 16 or packet[0] != DHAN_FEED_CODE_TICKER:
        return None

    try:
        price = struct.unpack_from("<f", packet, 8)[0]
        traded_at = struct.unpack_from("<i", packet, 12)[0]
    except struct.error:
        return None

    if not price or price <= 0:
        return None

    if traded_at > 0:
        timestamp = int(traded_at) - IST_OFFSET_SECONDS
    else:
        timestamp = int(datetime.now(timezone.utc).timestamp())

    return {
        "price": round(float(price), 4),
        "timestamp": timestamp,
    }


async def _dhan_tick_stream(identity: Dict[str, str]):
    """Yield live ticks from Dhan's market feed until it closes or goes idle.

    The server pings every 10s and drops the connection after 40s without a
    response; the websockets client answers control frames automatically.
    """
    url = _build_dhan_feed_ws_url()
    subscribe = _build_feed_subscribe_payload(identity)

    async with websockets.connect(
        url,
        open_timeout=DHAN_FEED_CONNECT_TIMEOUT_SEC,
        close_timeout=5,
        ping_interval=None,
        max_size=None,
    ) as feed:
        await feed.send(json.dumps(subscribe))

        while True:
            try:
                frame = await asyncio.wait_for(feed.recv(), timeout=DHAN_FEED_IDLE_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                return

            if not isinstance(frame, (bytes, bytearray)):
                continue

            for packet in _split_feed_packets(bytes(frame)):
                if packet[0] == DHAN_FEED_CODE_DISCONNECT:
                    return

                tick = _parse_ticker_packet(packet)
                if tick:
                    yield tick


def _build_dhan_full_depth_ws_url(limit: int) -> str:
    access_token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()

    if not access_token or not client_id:
        raise HTTPException(
            status_code=500,
            detail="Market data credentials are not configured. Set DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID.",
        )

    base = DHAN_FULL_DEPTH_200_WS_URL if limit >= 200 else DHAN_FULL_DEPTH_20_WS_URL
    query = urlencode(
        {
            "token": access_token,
            "clientId": client_id,
            "authType": 2,
        }
    )
    return f"{base}?{query}"


def _build_dhan_full_depth_subscribe_payload(identity: Dict[str, str], limit: int) -> dict:
    if limit >= 200:
        return {
            "RequestCode": 23,
            "ExchangeSegment": identity["exchangeSegment"],
            "SecurityId": str(identity["securityId"]),
        }

    return {
        "RequestCode": 23,
        "InstrumentCount": 1,
        "InstrumentList": [
            {
                "ExchangeSegment": identity["exchangeSegment"],
                "SecurityId": str(identity["securityId"]),
            }
        ],
    }


def _split_full_depth_packets(frame: bytes) -> list[bytes]:
    packets: list[bytes] = []
    offset = 0
    n = len(frame)

    while offset + 2 <= n:
        msg_len = int.from_bytes(frame[offset:offset + 2], "little", signed=False)
        if msg_len < 12 or (offset + msg_len) > n:
            break
        packets.append(frame[offset:offset + msg_len])
        offset += msg_len

    if packets:
        return packets

    if frame:
        return [frame]

    return []


def _parse_full_depth_packet(packet: bytes) -> tuple[Optional[str], list[dict]]:
    if len(packet) < 12:
        return None, []

    response_code = packet[2]
    side: Optional[str]
    if response_code == 41:
        side = "buy"
    elif response_code == 51:
        side = "sell"
    else:
        return None, []

    payload = packet[12:]
    row_size = 16
    available_rows = len(payload) // row_size
    if available_rows <= 0:
        return side, []

    rows: list[dict] = []
    for i in range(available_rows):
        chunk = payload[i * row_size:(i + 1) * row_size]
        if len(chunk) < row_size:
            continue

        try:
            price = float(struct.unpack("<d", chunk[0:8])[0])
            quantity = int.from_bytes(chunk[8:12], "little", signed=False)
            orders = int.from_bytes(chunk[12:16], "little", signed=False)
        except Exception:
            continue

        # Ignore empty depth rows emitted as zeroed packets.
        if price <= 0 and quantity <= 0 and orders <= 0:
            continue

        rows.append(
            {
                "price": round(price, 4),
                "quantity": quantity,
                "orders": orders,
            }
        )

    return side, rows


async def _fetch_full_depth_from_ws(identity: Dict[str, str], limit: int) -> dict:
    ws_url = _build_dhan_full_depth_ws_url(limit)
    subscribe_payload = _build_dhan_full_depth_subscribe_payload(identity, limit)

    buy_rows: list[dict] = []
    sell_rows: list[dict] = []

    try:
        async with asyncio.timeout(max(2.0, DHAN_FULL_DEPTH_TIMEOUT_SEC)):
            async with websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=2,
                max_size=4_000_000,
            ) as ws:
                await ws.send(json.dumps(subscribe_payload))

                while True:
                    message = await ws.recv()

                    if isinstance(message, str):
                        continue
                    if not isinstance(message, (bytes, bytearray)):
                        continue

                    for packet in _split_full_depth_packets(bytes(message)):
                        side, rows = _parse_full_depth_packet(packet)
                        if side == "buy" and rows:
                            buy_rows = rows
                        elif side == "sell" and rows:
                            sell_rows = rows

                    if buy_rows and sell_rows:
                        break
    except TimeoutError:
        raise HTTPException(status_code=502, detail="Timed out while receiving full market depth")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to fetch full market depth: {str(exc)}")

    if not buy_rows and not sell_rows:
        raise HTTPException(status_code=502, detail="Market depth feed returned no market depth rows")

    return {
        "buy": buy_rows[:limit],
        "sell": sell_rows[:limit],
    }


def _to_lightweight_candles(raw: dict) -> list[dict]:
    ts = raw.get("timestamp") if isinstance(raw, dict) else []
    opens = raw.get("open") if isinstance(raw, dict) else []
    highs = raw.get("high") if isinstance(raw, dict) else []
    lows = raw.get("low") if isinstance(raw, dict) else []
    closes = raw.get("close") if isinstance(raw, dict) else []

    if not all(isinstance(arr, list) for arr in [ts, opens, highs, lows, closes]):
        return []

    limit = min(len(ts), len(opens), len(highs), len(lows), len(closes))
    candles: list[dict] = []
    for idx in range(limit):
        t = _to_int(ts[idx])
        o = _to_float(opens[idx])
        h = _to_float(highs[idx])
        l = _to_float(lows[idx])
        c = _to_float(closes[idx])
        if t is None or o is None or h is None or l is None or c is None:
            continue
        candles.append(
            {
                "time": t,
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(l, 4),
                "close": round(c, 4),
            }
        )

    return candles


def _chart_last_tick_key(identity: Dict[str, str], timeframe: str) -> str:
    return (
        "dhan:chart:last_tick:"
        f"{identity['symbol'].lower()}:"
        f"{identity['exchangeSegment'].lower()}:"
        f"{identity['securityId']}:"
        f"{str(timeframe)}"
    )


async def _store_last_tick(identity: Dict[str, str], timeframe: str, payload: Dict[str, Union[int, float]]) -> None:
    key = _chart_last_tick_key(identity, timeframe)
    _chart_last_tick_memory[key] = payload
    await cache_set_json(key, payload, max(30, CHART_LAST_TICK_TTL))


async def _read_last_tick(identity: Dict[str, str], timeframe: str) -> Optional[Dict[str, Union[int, float]]]:
    candidate_timeframes = [str(timeframe)]
    if str(timeframe) != "5":
        candidate_timeframes.append("5")

    for tf in candidate_timeframes:
        key = _chart_last_tick_key(identity, tf)
        stale = await cache_get_json(key)
        if isinstance(stale, dict):
            return stale
        mem = _chart_last_tick_memory.get(key)
        if isinstance(mem, dict):
            return mem

    return None


@router.get("/status")
async def dhan_status():
    configured = bool(os.getenv("DHAN_ACCESS_TOKEN")) and bool(os.getenv("DHAN_CLIENT_ID"))
    redis_ok = await ping_redis()
    return {"configured": configured, "redis_connected": redis_ok}


@router.post("/quote/ltp")
async def dhan_ltp_quote(
    payload: SecuritiesRequest,
):
    return await _cached_dhan_post("/marketfeed/ltp", payload.securities, "quote")


@router.post("/quote/ohlc")
async def dhan_ohlc_quote(
    payload: SecuritiesRequest,
):
    return await _cached_dhan_post("/marketfeed/ohlc", payload.securities, "quote")


@router.post("/quote/full")
async def dhan_full_quote(
    payload: SecuritiesRequest,
):
    return await _cached_dhan_post("/marketfeed/quote", payload.securities, "quote")


@router.get("/quote/depth")
async def dhan_market_depth(
    symbol: str = Query(...),
    limit: int = Query(20, ge=1, le=200),
    securityId: Optional[str] = Query(None),
    exchangeSegment: Optional[str] = Query(None),
    instrument: Optional[str] = Query(None),
):
    identity = await _resolve_chart_identity(symbol, securityId, exchangeSegment, instrument)

    # Dhan Full Market Depth (20/200) is a binary websocket feed.
    full_depth_error: Optional[str] = None
    if limit >= 20:
        try:
            full_depth = await _fetch_full_depth_from_ws(identity, 200 if limit >= 200 else 20)
            return {
                "symbol": identity["symbol"],
                "identity": identity,
                "source": "live",
                "mode": "full_depth_ws",
                "limit": limit,
                "buy": full_depth["buy"][:limit],
                "sell": full_depth["sell"][:limit],
            }
        except HTTPException as exc:
            full_depth_error = exc.detail if isinstance(exc.detail, str) else "Full depth feed unavailable"

    quote_payload = {
        identity["exchangeSegment"]: [_security_id_for_quote_payload(identity["securityId"])],
    }
    response = await _cached_dhan_post("/marketfeed/quote", quote_payload, "quote")
    depth = _extract_depth_from_quote(
        raw_payload=response.get("data") or {},
        exchange_segment=identity["exchangeSegment"],
        security_id=identity["securityId"],
        limit=limit,
    )

    return {
        "symbol": identity["symbol"],
        "identity": identity,
        "source": response.get("source"),
        "mode": "quote_snapshot",
        "limit": limit,
        "actualDepthLevels": max(len(depth["buy"]), len(depth["sell"])),
        "fallbackReason": full_depth_error,
        "buy": depth["buy"],
        "sell": depth["sell"],
    }


@router.post("/historical/daily")
async def dhan_historical_daily(
    payload: HistoricalDailyRequest,
):
    return await _cached_dhan_post("/charts/historical", payload.model_dump(), "history")


@router.post("/historical/intraday")
async def dhan_historical_intraday(
    payload: HistoricalIntradayRequest,
):
    return await _cached_dhan_post("/charts/intraday", payload.model_dump(), "history")


@router.post("/options/chain")
async def dhan_option_chain(
    payload: OptionChainRequest,
):
    return await _cached_dhan_post("/optionchain", payload.model_dump(), "options")


@router.post("/options/expiry-list")
async def dhan_expiry_list(
    payload: ExpiryListRequest,
):
    return await _cached_dhan_post("/optionchain/expirylist", payload.model_dump(), "options")


@router.post("/options/expired-rolling")
async def dhan_expired_rolling_options(
    payload: ExpiredOptionsRequest,
):
    return await _cached_dhan_post("/charts/rollingoption", payload.model_dump(), "history")


async def _fetch_last_available_session(
    identity: Dict[str, str],
    timeframe: str,
    max_lookback: int = CHART_SESSION_LOOKBACK_DAYS,
) -> tuple[list[dict], Optional[date]]:
    """Walk back trading days until a session with candles is found.

    Dhan can return an empty intraday payload for the most recent session (no
    ticks yet, or a day NSE reports as open but has no data), which would leave
    the chart blank while the market is closed. Searching earlier sessions
    guarantees the UI always has something to render.
    """
    interval_min = _resolve_timeframe(timeframe)
    day = _previous_trading_day(_get_intraday_session_day(datetime.now(IST)))

    for _ in range(max(1, max_lookback)):
        from_dt, to_dt = _session_window(day, interval_min)
        payload = _build_intraday_payload(identity, timeframe, from_dt, to_dt)
        try:
            response = await _cached_dhan_post("/charts/intraday", payload, "history")
        except HTTPException:
            day = _previous_trading_day(day)
            continue

        candles = _to_lightweight_candles(response.get("data") or {})
        if candles:
            return candles, day

        day = _previous_trading_day(day)

    return [], None


@router.get("/chart/bootstrap")
async def dhan_chart_bootstrap(
    symbol: str = Query(...),
    timeframe: str = Query("5"),
    securityId: Optional[str] = Query(None),
    exchangeSegment: Optional[str] = Query(None),
    instrument: Optional[str] = Query(None),
):
    identity = await _resolve_chart_identity(symbol, securityId, exchangeSegment, instrument)
    requested_timeframe = str(timeframe).strip().upper()
    resolved_timeframe = requested_timeframe
    session_date: Optional[date] = None
    is_fallback_session = False

    if requested_timeframe == CHART_DAILY_TIMEFRAME:
        payload = _build_daily_historical_payload(identity)
        response = await _cached_dhan_post("/charts/historical", payload, "history")
    else:
        payload = _build_intraday_payload(identity, resolved_timeframe)
        try:
            response = await _cached_dhan_post("/charts/intraday", payload, "history")
        except HTTPException as exc:
            # Dhan intermittently rejects 1-minute intraday for some equity symbols.
            # Fall back to 5-minute candles so the UI can still render a live chart.
            if exc.status_code == 502 and requested_timeframe == "1":
                resolved_timeframe = "5"
                payload = _build_intraday_payload(identity, resolved_timeframe)
                response = await _cached_dhan_post("/charts/intraday", payload, "history")
            else:
                raise

    candles = _to_lightweight_candles(response.get("data") or {})

    if requested_timeframe == CHART_DAILY_TIMEFRAME:
        try:
            candles = await _append_current_session_daily_candle(identity, candles)
        except Exception:
            # Keep historical candles if live append fails.
            pass
    else:
        # Smart default: an empty session (market closed, or a provider gap)
        # would leave the chart blank. Fall back to the most recent session
        # that actually has candles so there is always something to render.
        if not candles:
            fallback_candles, fallback_day = await _fetch_last_available_session(
                identity, resolved_timeframe
            )
            if fallback_candles:
                candles = fallback_candles
                session_date = fallback_day
                is_fallback_session = True

        candles = _fill_intraday_session_gaps(candles, resolved_timeframe)

    if requested_timeframe != CHART_DAILY_TIMEFRAME and candles:
        last_candle = candles[-1]
        last_tick_payload = {
            "timestamp": _to_int(last_candle.get("time")),
            "price": _to_float(last_candle.get("close")),
        }

        if last_tick_payload["timestamp"] and last_tick_payload["price"] and last_tick_payload["price"] > 0:
            await _store_last_tick(identity, requested_timeframe, last_tick_payload)
            if resolved_timeframe != requested_timeframe:
                await _store_last_tick(identity, resolved_timeframe, last_tick_payload)

    return {
        "symbol": identity["symbol"],
        "timeframe": requested_timeframe,
        "resolvedTimeframe": resolved_timeframe,
        "identity": identity,
        "source": response.get("source"),
        "sessionDate": _date_only(
            datetime(session_date.year, session_date.month, session_date.day, tzinfo=IST)
        ) if session_date else None,
        "isFallbackSession": is_fallback_session,
        "candles": candles,
    }


@router.get("/chart/history")
async def dhan_chart_history(
    symbol: str = Query(...),
    timeframe: str = Query("5"),
    fromDate: str = Query(..., description="Start date, YYYY-MM-DD (inclusive)"),
    toDate: str = Query(..., description="End date, YYYY-MM-DD (inclusive)"),
    securityId: Optional[str] = Query(None),
    exchangeSegment: Optional[str] = Query(None),
    instrument: Optional[str] = Query(None),
):
    """Static historical candles for an explicit window and interval.

    Unlike /chart/bootstrap this never stores a live tick or opens a stream, so
    it behaves identically whether the market is open or closed.
    """
    identity = await _resolve_chart_identity(symbol, securityId, exchangeSegment, instrument)
    requested_timeframe = str(timeframe).strip().upper()

    from_date = _parse_chart_date(fromDate, "fromDate")
    to_date = _parse_chart_date(toDate, "toDate")

    if from_date > to_date:
        raise HTTPException(status_code=400, detail="fromDate must be on or before toDate")

    today = datetime.now(IST).date()
    if from_date > today:
        raise HTTPException(status_code=400, detail="fromDate cannot be in the future")
    to_date = min(to_date, today)

    if requested_timeframe == CHART_DAILY_TIMEFRAME:
        # Dhan treats the daily toDate as non-inclusive; nudge so the user's
        # chosen end date is actually part of the result.
        payload = _build_daily_historical_payload(identity, from_date, to_date + timedelta(days=1))
        response = await _cached_dhan_post("/charts/historical", payload, "history")
        candles = _to_lightweight_candles(response.get("data") or {})
        source = response.get("source")
    else:
        interval_min = _resolve_timeframe(requested_timeframe)

        earliest = today - timedelta(days=CHART_INTRADAY_MAX_HISTORY_DAYS)
        if to_date < earliest:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Intraday history is only available for roughly the last "
                    f"{CHART_INTRADAY_MAX_HISTORY_DAYS // 365} years. "
                    "Use the daily (D) timeframe for older ranges."
                ),
            )
        from_date = max(from_date, earliest)

        window_start, _ = _session_window(from_date, interval_min)
        _, window_end = _session_window(to_date, interval_min)

        merged: Dict[int, dict] = {}
        source = None
        # Dhan caps intraday at 90 days per request, so chunk the window and merge.
        for chunk_start, chunk_end in _intraday_chunks(window_start, window_end):
            payload = _build_intraday_payload(identity, requested_timeframe, chunk_start, chunk_end)
            chunk_response = await _cached_dhan_post("/charts/intraday", payload, "history")
            source = source or chunk_response.get("source")
            for candle in _to_lightweight_candles(chunk_response.get("data") or {}):
                ts = _to_int(candle.get("time"))
                if ts is not None:
                    merged[ts] = candle

        # No-ops for multi-day ranges; fills gaps when the range is one session.
        candles = _fill_intraday_session_gaps([merged[ts] for ts in sorted(merged)], requested_timeframe)

    return {
        "symbol": identity["symbol"],
        "timeframe": requested_timeframe,
        "resolvedTimeframe": requested_timeframe,
        "identity": identity,
        "source": source,
        "mode": "history",
        "fromDate": _date_only(datetime(from_date.year, from_date.month, from_date.day, tzinfo=IST)),
        "toDate": _date_only(datetime(to_date.year, to_date.month, to_date.day, tzinfo=IST)),
        "candles": candles,
    }


@router.get("/chart/latest")
async def dhan_chart_latest(
    symbol: str = Query(...),
    timeframe: str = Query("5"),
    securityId: Optional[str] = Query(None),
    exchangeSegment: Optional[str] = Query(None),
    instrument: Optional[str] = Query(None),
):
    identity = await _resolve_chart_identity(symbol, securityId, exchangeSegment, instrument)
    _resolve_timeframe(timeframe)

    quote_payload = {
        identity["exchangeSegment"]: [_security_id_for_quote_payload(identity["securityId"])],
    }

    try:
        response = await _cached_dhan_post("/marketfeed/ltp", quote_payload, "chart_tick")
        extracted = _extract_ltp_and_ts(response.get("data") or {}, identity["exchangeSegment"], identity["securityId"])
        source = response.get("source")
        await _store_last_tick(
            identity,
            timeframe,
            {
                "timestamp": extracted["timestamp"],
                "price": extracted["price"],
            },
        )
    except HTTPException:
        stale = await _read_last_tick(identity, timeframe)
        if not isinstance(stale, dict):
            raise

        stale_ts = _to_int(stale.get("timestamp"))
        stale_price = _to_float(stale.get("price"))
        if stale_ts is None or stale_price is None or stale_price <= 0:
            raise

        extracted = {
            "timestamp": stale_ts,
            "price": round(stale_price, 4),
        }
        source = "stale_cache"

    event_payload = {
        "event": "chart_tick",
        "symbol": identity["symbol"],
        "timeframe": str(timeframe),
        "timestamp": extracted["timestamp"],
        "price": extracted["price"],
        "source": source,
    }
    await publish_json(_stream_channel(f"chart:{identity['symbol'].lower()}:{timeframe}"), event_payload)

    return {
        "identity": identity,
        **event_payload,
    }


@router.websocket("/chart/ws")
async def dhan_chart_ws(websocket: WebSocket):
    await websocket.accept()

    symbol = str(websocket.query_params.get("symbol", "")).strip().upper()
    timeframe = str(websocket.query_params.get("timeframe", "5")).strip().upper()
    security_id = websocket.query_params.get("securityId")
    exchange_segment = websocket.query_params.get("exchangeSegment")
    instrument = websocket.query_params.get("instrument")

    if not symbol:
        await websocket.send_json({"event": "error", "detail": "Symbol is required"})
        await websocket.close(code=1008)
        return

    if timeframe == CHART_DAILY_TIMEFRAME:
        await websocket.send_json(
            {
                "event": "error",
                "detail": "Daily timeframe is not streamable. Use chart/bootstrap for daily candles.",
            }
        )
        await websocket.close(code=1008)
        return

    try:
        _resolve_timeframe(timeframe)
    except HTTPException as exc:
        await websocket.send_json({"event": "error", "detail": exc.detail})
        await websocket.close(code=1008)
        return

    try:
        identity = await _resolve_chart_identity(symbol, security_id, exchange_segment, instrument)
    except HTTPException as exc:
        await websocket.send_json({"event": "error", "detail": exc.detail})
        await websocket.close(code=1008)
        return

    await websocket.send_json(
        {
            "event": "subscribed",
            "symbol": symbol,
            "timeframe": timeframe,
        }
    )

    # Preferred path: Dhan's real-time binary feed pushes every trade, so there
    # is no polling interval to wait on.
    try:
        async for tick in _dhan_tick_stream(identity):
            payload = {
                "event": "chart_tick",
                "symbol": identity["symbol"],
                "timeframe": str(timeframe),
                "timestamp": tick["timestamp"],
                "price": tick["price"],
                "source": "feed",
            }
            await _store_last_tick(identity, timeframe, {
                "timestamp": tick["timestamp"],
                "price": tick["price"],
            })
            await publish_json(
                _stream_channel(f"chart:{identity['symbol'].lower()}:{timeframe}"), payload
            )
            await websocket.send_json({"identity": identity, **payload})
    except WebSocketDisconnect:
        return
    except Exception as exc:  # feed unavailable / auth rejected / connection dropped
        await websocket.send_json(
            {
                "event": "stream_warning",
                "symbol": symbol,
                "timeframe": timeframe,
                "detail": f"Live feed unavailable ({type(exc).__name__}); falling back to polling.",
            }
        )

    # Fallback path: poll the LTP REST endpoint on an interval.
    failures = 0
    try:
        while True:
            try:
                tick = await dhan_chart_latest(
                    symbol=symbol,
                    timeframe=timeframe,
                    securityId=security_id,
                    exchangeSegment=exchange_segment,
                    instrument=instrument,
                )
                await websocket.send_json(tick)
                failures = 0
            except HTTPException as exc:
                failures += 1
                await websocket.send_json(
                    {
                        "event": "stream_warning",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "detail": exc.detail,
                        "failures": failures,
                    }
                )

            await asyncio.sleep(1.5)
    except WebSocketDisconnect:
        return


@router.post("/cache/warm")
async def warm_market_cache(
    payload: CacheWarmRequest,
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admin users can warm the shared cache")

    if not payload.jobs:
        return {"warmed": 0, "results": []}

    if len(payload.jobs) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 warm jobs per request")

    results = []
    for index, job in enumerate(payload.jobs):
        if job.endpoint not in ALLOWED_WARM_ENDPOINTS.get(job.bucket, set()):
            results.append(
                {
                    "index": index,
                    "bucket": job.bucket,
                    "endpoint": job.endpoint,
                    "ok": False,
                    "error": "Endpoint is not allowed for this bucket",
                }
            )
            continue

        try:
            response = await _cached_dhan_post(job.endpoint, job.payload, job.bucket)
            results.append(
                {
                    "index": index,
                    "bucket": job.bucket,
                    "endpoint": job.endpoint,
                    "ok": True,
                    "source": response.get("source"),
                }
            )
        except HTTPException as exc:
            results.append(
                {
                    "index": index,
                    "bucket": job.bucket,
                    "endpoint": job.endpoint,
                    "ok": False,
                    "error": exc.detail,
                }
            )

    warmed = sum(1 for r in results if r.get("ok"))
    return {"warmed": warmed, "total": len(results), "results": results}


@router.post("/stream/publish")
async def publish_market_event(
    payload: StreamPublishRequest,
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admin users can publish stream events")

    channel = _stream_channel(payload.bucket)
    published = await publish_json(
        channel,
        {
            "event": payload.event,
            "symbol": payload.symbol,
            "bucket": payload.bucket,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": payload.data,
        },
    )
    if not published:
        raise HTTPException(status_code=503, detail="Redis pub/sub is unavailable")

    return {"published": True, "channel": channel}


@router.websocket("/stream/ws")
async def market_stream_ws(websocket: WebSocket):
    requested = websocket.query_params.get("channels", "quote,options,history,broadcast")
    channels = []
    for raw in requested.split(","):
        name = raw.strip()
        if not name:
            continue
        channels.append(_stream_channel(name))

    channels = list(dict.fromkeys(channels))
    await websocket.accept()

    if not channels:
        await websocket.send_json({"error": "No channels requested"})
        await websocket.close(code=1008)
        return

    pubsub = await create_pubsub(channels)
    if pubsub is None:
        await websocket.send_json({"error": "Redis pub/sub unavailable"})
        await websocket.close(code=1013)
        return

    await websocket.send_json({"event": "subscribed", "channels": channels})

    heartbeat_every = 15
    idle_ticks = 0

    try:
        while True:
            message = await pubsub.get_message(timeout=1.0)
            if message and message.get("type") == "message":
                idle_ticks = 0
                data = message.get("data")
                if isinstance(data, str):
                    try:
                        await websocket.send_json(json.loads(data))
                    except json.JSONDecodeError:
                        await websocket.send_json({"event": "raw", "data": data})
                else:
                    await websocket.send_json({"event": "raw", "data": data})
            else:
                idle_ticks += 1
                if idle_ticks >= heartbeat_every:
                    idle_ticks = 0
                    await websocket.send_json(
                        {
                            "event": "heartbeat",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        return
    finally:
        await close_pubsub(pubsub, channels)
