"""
Market Data Router - Live SENSEX & NIFTY data proxy
"""

from fastapi import APIRouter, Depends
import asyncio
import httpx
import logging
import time
from datetime import datetime, timezone, timedelta, time as dtime
from models import User
from routers.auth import require_admin
from services.nse_mcp import SERVERS as NSE_MCP_SERVERS, McpSession
from services.instruments import get_instruments
from services.redis_store import cache_get_json, cache_set_json
from utils.market_utils import is_market_holiday

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/nse-mcp/probe")
async def nse_mcp_probe(_: User = Depends(require_admin)):
    """Admin check, run from wherever the backend is hosted: do NSE's MCP servers answer
    here, next to the NSE website API this app scrapes today (which Render gets 403 on)?"""
    report: dict = {}
    async with httpx.AsyncClient(timeout=20.0) as client:
        for name, url in NSE_MCP_SERVERS.items():
            started = time.perf_counter()
            try:
                session = McpSession(url, client)
                info = await session.initialize()
                tools = await session.list_tools()
                report[name] = {"ok": True, "server": info.get("serverInfo"), "tools": len(tools)}
                if name == "cmmkt":
                    report[name]["data_status"] = await session.call_tool("cm_get_data_status")
            except Exception as exc:
                report[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
            report[name]["ms"] = round((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        try:
            resp = await client.get("https://www.nseindia.com/api/marketStatus", headers=BROWSER_HEADERS)
            report["nse_website"] = {"ok": resp.status_code == 200, "status": resp.status_code}
        except Exception as exc:
            report["nse_website"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
        report["nse_website"]["ms"] = round((time.perf_counter() - started) * 1000)
    return report

# IST = UTC + 5:30
IST_OFFSET = timedelta(hours=5, minutes=30)
IST = timezone(IST_OFFSET)


def get_ist_now():
    """Get current time in IST"""
    return datetime.now(timezone.utc).astimezone(IST)


def get_market_status_fallback():
    """Fallback: Determine Indian market status based on current IST time"""
    now = get_ist_now()
    weekday = now.weekday()  # 0=Monday, 6=Sunday

    if weekday >= 5:
        return "Closed"

    time_minutes = now.hour * 60 + now.minute

    if time_minutes < 540:       # Before 9:00 AM
        return "Pre-Market"
    elif time_minutes < 555:     # 9:00 - 9:15
        return "Pre-Open"
    elif time_minutes <= 930:    # 9:15 - 15:30
        return "Open"
    else:
        return "Closed"


async def fetch_market_status(client: httpx.AsyncClient) -> str:
    """Fetch real market status from NSE API.

    NOTE: NSE's `marketStatus` field is unreliable — it frequently reports
    "Open" for every segment even when the market is closed (the `tradeDate`
    stays pinned to the previous session's close). The trustworthy signal is
    `marketStatusMessage` (e.g. "Normal Market has Closed" / "... is Open" /
    "Pre Open Market ..."). We read that, and fall back to the IST clock when
    the message is missing or ambiguous.
    """
    try:
        resp = await client.get(
            "https://www.nseindia.com/api/marketStatus",
            headers={
                **BROWSER_HEADERS,
                "Referer": "https://www.nseindia.com/",
                "Origin": "https://www.nseindia.com",
            },
        )
        if resp.status_code == 200:
            data = resp.json()
            states = data.get("marketState", [])
            for state in states:
                if state.get("market") == "Capital Market":
                    message = str(state.get("marketStatusMessage", "")).strip().lower()
                    if "closed" in message or "close" in message:
                        return "Closed"
                    if "pre" in message and "open" in message:
                        return "Pre-Open"
                    if "open" in message:
                        return "Open"
                    # Message missing/unrecognized — trust the IST clock instead
                    # of the unreliable marketStatus flag.
                    return get_market_status_fallback()
    except Exception:
        pass
    return get_market_status_fallback()


BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


@router.get("/session-status")
async def get_market_session_status():
    """Lightweight endpoint for polling decisions: market open/closed with trading-day context."""
    ist_now = get_ist_now()
    today = ist_now.date()
    holiday_or_weekend = is_market_holiday(today)

    if holiday_or_weekend:
        return {
            "market_status": "Closed",
            "is_open": False,
            "is_trading_day": False,
            "reason": "holiday_or_weekend",
            "timestamp": ist_now.isoformat(),
        }

    async with httpx.AsyncClient(timeout=6.0) as client:
        market_status = await fetch_market_status(client)

    normalized = str(market_status or "").strip().lower()
    is_open = normalized == "open"

    return {
        "market_status": market_status,
        "is_open": is_open,
        "is_trading_day": True,
        "reason": "nse_market_status" if market_status else "fallback",
        "timestamp": ist_now.isoformat(),
    }


@router.get("/live")
async def get_live_market_data():
    """Get live SENSEX and NIFTY data"""
    ist_now = get_ist_now()
    sensex_data = None
    nifty_data = None
    market_status = get_market_status_fallback()  # default
    debug = {
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "ist": ist_now.strftime("%Y-%m-%d %H:%M:%S"),
        "weekday": ist_now.weekday(),
        "time_minutes": ist_now.hour * 60 + ist_now.minute,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Fetch real market status from NSE
        market_status = await fetch_market_status(client)

        # ── BSE SENSEX ──
        # Response format: [{"indxnm":"SenSexValue","ltp":"81,287.19","chg":"-961.42","perchg":"-1.17",...}]
        try:
            resp = await client.get(
                "https://api.bseindia.com/RealTimeBseIndiaAPI/api/GetSensexData/w",
                headers={
                    **BROWSER_HEADERS,
                    "Referer": "https://www.bseindia.com/",
                    "Origin": "https://www.bseindia.com",
                },
            )
            if resp.status_code == 200:
                raw = resp.json()
                item = raw[0] if isinstance(raw, list) and len(raw) > 0 else raw if isinstance(raw, dict) else None
                if item:
                    sensex_data = {
                        "name": "SENSEX",
                        "value": item.get("ltp", "0"),
                        "change": item.get("chg", "0"),
                        "pct_change": item.get("perchg", "0"),
                        "high": item.get("High", "0"),
                        "low": item.get("Low", "0"),
                        "open": item.get("I_open", "0"),
                        "prev_close": item.get("Prev_Close", "0"),
                    }
        except Exception as e:
            debug["bse_error"] = str(e)

        # ── NSE NIFTY 50 ──
        # Response format: {"data":[{"indexName":"NIFTY 50","last":25178.65,"percChange":-1.25,...}]}
        try:
            resp = await client.get(
                "https://www.nseindia.com/api/NextApi/apiClient?functionName=getIndexData&&type=All",
                headers={
                    **BROWSER_HEADERS,
                    "Referer": "https://www.nseindia.com/",
                    "Origin": "https://www.nseindia.com",
                },
            )
            if resp.status_code == 200:
                raw = resp.json()
                # data can be at root level or inside "data" key
                indices = raw.get("data", raw) if isinstance(raw, dict) else raw
                if isinstance(indices, list):
                    for idx in indices:
                        if idx.get("indexName") == "NIFTY 50":
                            last_val = idx.get("last", 0)
                            prev_close = idx.get("previousClose", 0)
                            try:
                                change_val = round(float(last_val) - float(prev_close), 2)
                            except (ValueError, TypeError):
                                change_val = 0
                            nifty_data = {
                                "name": "NIFTY 50",
                                "value": str(last_val),
                                "change": str(change_val),
                                "pct_change": str(idx.get("percChange", 0)),
                                "high": str(idx.get("high", 0)),
                                "low": str(idx.get("low", 0)),
                                "open": str(idx.get("open", 0)),
                                "prev_close": str(prev_close),
                            }
                            break
            else:
                debug["nse_status"] = resp.status_code
                debug["nse_body"] = resp.text[:200]
        except Exception as e:
            debug["nse_error"] = str(e)

    return {
        "market_status": market_status,
        "sensex": sensex_data,
        "nifty": nifty_data,
        "timestamp": ist_now.isoformat(),
        "debug": debug,
    }


# Ticker indices: display label -> candidate NSE `indexName` values (matched case-insensitively).
INDEX_TICKER_CONFIG = [
    {"display": "NIFTY 50", "match": ["nifty 50"]},
    {"display": "BANKNIFTY", "match": ["nifty bank"]},
    {"display": "FINNIFTY", "match": ["nifty financial services", "nifty fin service", "nifty fin services"]},
    {"display": "MIDCPNIFTY", "match": ["nifty midcap select"]},
    {"display": "NIFTY IT", "match": ["nifty it"]},
    {"display": "NIFTY NEXT 50", "match": ["nifty next 50"]},
]


def _to_float(value) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError, AttributeError):
        return 0.0


@router.get("/indices")
async def get_indices():
    """Live index snapshot for the ticker strip: BSE SENSEX + NSE indices.

    Public (no auth) so the landing page can render it pre-login. Falls back
    gracefully to whatever sources respond; the client keeps its own defaults
    if this returns nothing.
    """
    ist_now = get_ist_now()
    results = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        market_status = await fetch_market_status(client)

        # ── BSE SENSEX ──
        try:
            resp = await client.get(
                "https://api.bseindia.com/RealTimeBseIndiaAPI/api/GetSensexData/w",
                headers={**BROWSER_HEADERS, "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"},
            )
            if resp.status_code == 200:
                raw = resp.json()
                item = raw[0] if isinstance(raw, list) and raw else raw if isinstance(raw, dict) else None
                if item:
                    pct = _to_float(item.get("perchg"))
                    results.append({
                        "symbol": "SENSEX",
                        "value": _to_float(item.get("ltp")),
                        "change": _to_float(item.get("chg")),
                        "pct_change": round(pct, 2),
                        "up": pct >= 0,
                    })
        except Exception:
            pass

        # ── NSE indices (getIndexData returns ALL indices) ──
        nse_by_name = {}
        try:
            resp = await client.get(
                "https://www.nseindia.com/api/NextApi/apiClient?functionName=getIndexData&&type=All",
                headers={**BROWSER_HEADERS, "Referer": "https://www.nseindia.com/", "Origin": "https://www.nseindia.com"},
            )
            if resp.status_code == 200:
                raw = resp.json()
                indices = raw.get("data", raw) if isinstance(raw, dict) else raw
                if isinstance(indices, list):
                    for idx in indices:
                        name = str(idx.get("indexName", "")).strip().lower()
                        if name:
                            nse_by_name[name] = idx
        except Exception:
            pass

    for cfg in INDEX_TICKER_CONFIG:
        idx = next((nse_by_name[c] for c in cfg["match"] if c in nse_by_name), None)
        if not idx:
            continue
        last = _to_float(idx.get("last"))
        prev = _to_float(idx.get("previousClose"))
        pct = _to_float(idx.get("percChange"))
        results.append({
            "symbol": cfg["display"],
            "value": last,
            "change": round(last - prev, 2) if prev else 0.0,
            "pct_change": round(pct, 2),
            "up": pct >= 0,
        })

    return {
        "market_status": market_status,
        "indices": results,
        "timestamp": ist_now.isoformat(),
    }


NSE_HEADERS = {**BROWSER_HEADERS, "Referer": "https://www.nseindia.com/", "Origin": "https://www.nseindia.com"}
MOVERS_FRESH_LIVE = 20        # market hours: everyone shares one NSE call every 20 seconds
MOVERS_FRESH_CLOSED = 1800    # after the close the lists don't change
MOVERS_KEEP = 3 * 86400       # the last good copy outlives an NSE outage
_movers_locks = {"gainers": asyncio.Lock(), "losers": asyncio.Lock()}


def _market_hours_now() -> bool:
    now = get_ist_now()
    return now.weekday() < 5 and not is_market_holiday(now.date()) and dtime(9, 0) <= now.time() <= dtime(15, 45)


async def _nse_gainers() -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get("https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getTopTenStock", headers=NSE_HEADERS)
        resp.raise_for_status()
    return [{
        "symbol": g.get("symbol", ""),
        "price": g.get("lastPrice", 0),
        "change": round(float(g.get("change", 0)), 2),
        "pct_change": round(float(g.get("pchange", 0)), 2),
        "volume": g.get("totalTradedVolume", 0),
    } for g in resp.json().get("topGainers", [])]


async def _nse_losers() -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get("https://www.nseindia.com/api/live-analysis-variations?index=loosers", headers=NSE_HEADERS)
        resp.raise_for_status()
    results = []
    for item in resp.json().get("NIFTY", {}).get("data", [])[:10]:
        price = float(item.get("ltp", 0))
        prev = float(item.get("prev_price", 0))
        results.append({
            "symbol": item.get("symbol", ""),
            "price": price,
            "change": round(price - prev, 2),
            "pct_change": round(float(item.get("perChange", 0)), 2),
            "volume": item.get("trade_quantity", 0),
        })
    return results


async def _bhavcopy_movers(kind: str) -> list[dict]:
    """Last resort: the latest session's biggest moves from the NSE bhavcopy, over the same stocks
    NSE's lists use (gainers: the whole market; losers: NIFTY 50)."""
    from routers.stocks import _index_members, _latest_bhav_prices, constituent_moves

    _, prices = await _latest_bhav_prices()
    members = [{"symbol": s, "industry": ""} for s in prices] if kind == "gainers" else await _index_members("nifty50")
    rows = [r for r in constituent_moves(members, prices)["rows"] if r["pct"] is not None]
    picked = [r for r in rows if r["pct"] > 0] if kind == "gainers" else [r for r in reversed(rows) if r["pct"] < 0]
    return [{"symbol": r["symbol"], "price": r["close"], "change": r["change"], "pct_change": r["pct"], "volume": 0} for r in picked[:10]]


async def shared_movers(kind: str) -> list[dict]:
    """Top gainers or losers for every user from one shared copy in Redis: NSE is asked at most once
    every 20 seconds in market hours (every 30 min after the close). If NSE fails, the last good copy is
    served, or the bhavcopy's movers when there is none; either way NSE is retried a minute later."""
    key = f"movers:{kind}"
    fresh = MOVERS_FRESH_LIVE if _market_hours_now() else MOVERS_FRESH_CLOSED
    cached = await cache_get_json(key)
    if cached and time.time() - cached["at"] < fresh:
        return cached["items"]
    async with _movers_locks[kind]:
        cached = await cache_get_json(key)  # another request may have refreshed it meanwhile
        if cached and time.time() - cached["at"] < fresh:
            return cached["items"]
        try:
            items = await (_nse_gainers() if kind == "gainers" else _nse_losers())
        except Exception as exc:
            logger.warning("NSE %s failed: %s", kind, exc)
            items = []
        retry_at = time.time() - fresh + 60  # stamp a fallback so NSE is asked again in a minute
        if items:
            await cache_set_json(key, {"at": time.time(), "items": items}, MOVERS_KEEP)
            return items
        if cached:
            await cache_set_json(key, {"at": retry_at, "items": cached["items"]}, MOVERS_KEEP)
            return cached["items"]
        try:
            items = await _bhavcopy_movers(kind)
        except Exception as exc:
            logger.warning("bhavcopy %s failed: %s", kind, exc)
            return []
        if items:
            await cache_set_json(key, {"at": retry_at, "items": items}, MOVERS_KEEP)
        return items


async def _with_names(items: list[dict]) -> list[dict]:
    """Company names for the dashboard list, from the in-memory instrument list."""
    instruments = await get_instruments()
    return [{**m, "name": (instruments.get(m["symbol"]) or {}).get("name", "")} for m in items]


@router.get("/top-stocks")
async def get_top_stocks():
    """Top 10 gainers (shared cache, see shared_movers)."""
    return {"gainers": await _with_names(await shared_movers("gainers"))}


@router.get("/top-losers")
async def get_top_losers():
    """Top 10 NIFTY losers (shared cache, see shared_movers)."""
    return {"losers": await _with_names(await shared_movers("losers"))}
