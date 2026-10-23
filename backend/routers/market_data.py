"""
Market Data Router - Live SENSEX & NIFTY data proxy
"""

from fastapi import APIRouter, Depends
import asyncio
import httpx
import logging
import time
from datetime import datetime, timezone, timedelta, time as dtime
from typing import Optional
from urllib.parse import quote
from models import User
from routers.auth import require_admin
from services.nse_mcp import SERVERS as NSE_MCP_SERVERS, McpSession
from services.instruments import get_instruments
from services.redis_store import cache_get_json, cache_get_many, cache_set_json
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
NSE_API = "https://www.nseindia.com/api"
# Movers groups. All but TotalMarket are NSE's own lists (live-analysis-variations); NIFTY 50 is
# NSE's default. TotalMarket ("All NIFTY", the ~750-stock Nifty Total Market) is ranked by us.
MOVER_GROUPS = {
    "NIFTY": "NIFTY 50", "BANKNIFTY": "Bank Nifty", "NIFTYNEXT50": "NIFTY Next 50", "TotalMarket": "All NIFTY",
    "FOSec": "F&O stocks", "allSec": "All stocks",
}
# Member lists (nsearchives ind_<name>list.csv); Total Market's file name has an extra underscore.
_GROUP_INDEX_CSV = {"NIFTY": "nifty50", "BANKNIFTY": "niftybank", "NIFTYNEXT50": "niftynext50",
                    "TotalMarket": "niftytotalmarket_"}
MOVERS_FRESH_LIVE = 20        # pre-open, session and closing: everyone shares one NSE call every 20 seconds
MOVERS_FRESH_CLOSED = 1800    # after NSE's 16:00 final values the lists don't change
MOVERS_KEEP = 3 * 86400       # the last good copy outlives an NSE outage
SPARK_POINTS = 60
_movers_locks: dict[str, asyncio.Lock] = {}
_spark_gate = asyncio.Semaphore(4)


def market_phase(now: Optional[datetime] = None) -> str:
    """pre_open 09:00-09:15, open 09:15-15:30, closing 15:30-16:05 (NSE publishes its final, VWAP-based
    closing prices at 16:00), else closed. Weekends and NSE holidays are closed."""
    now = now or get_ist_now()
    if now.weekday() >= 5 or is_market_holiday(now.date()):
        return "closed"
    t = now.time()
    if dtime(9, 0) <= t < dtime(9, 15):
        return "pre_open"
    if dtime(9, 15) <= t < dtime(15, 30):
        return "open"
    if dtime(15, 30) <= t < dtime(16, 5):
        return "closing"
    return "closed"


def _nse_time(text: Optional[str]) -> Optional[datetime]:
    """NSE's "23-Oct-2026 16:00:00" (IST) as an aware datetime."""
    try:
        return datetime.strptime(str(text).strip().title(), "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
    except ValueError:
        return None


def _mover(symbol: str, price, prev, pct, volume) -> dict:
    price, prev = float(price or 0), float(prev or 0)
    return {"symbol": symbol, "price": price, "prev_close": prev, "change": round(price - prev, 2),
            "pct_change": round(float(pct or 0), 2), "volume": int(float(volume or 0))}


def rank_groups(rows: list[dict], fno: Optional[list[dict]], members: dict[str, set]) -> dict:
    """Top 10 gainers and losers of every NSE group from one market-wide list (pre-open, bhavcopy).
    Index groups use their member lists; F&O uses its own list, when there is one."""
    pools = {g: [r for r in rows if r["symbol"] in members.get(g, ())] for g in _GROUP_INDEX_CSV}
    pools.update(FOSec=fno or [], allSec=rows)
    out = {}
    for group, pool in pools.items():
        ranked = sorted(pool, key=lambda r: r["pct_change"], reverse=True)
        out[group] = {"gainers": [r for r in ranked if r["pct_change"] > 0][:10],
                      "losers": [r for r in reversed(ranked) if r["pct_change"] < 0][:10]}
    return out


async def _group_members() -> dict[str, set]:
    from routers.stocks import _index_members

    return {g: {m["symbol"] for m in await _index_members(csv)} for g, csv in _GROUP_INDEX_CSV.items()}


async def _nse_variations() -> dict:
    """NSE's session movers for every group: two calls (gainers, losers) carry all seven groups."""
    groups, as_of = {}, None
    async with httpx.AsyncClient(timeout=10.0, headers=NSE_HEADERS) as client:
        for kind, param in (("gainers", "gainers"), ("losers", "loosers")):
            resp = await client.get(f"{NSE_API}/live-analysis-variations?index={param}")
            resp.raise_for_status()
            data = resp.json()
            for group in MOVER_GROUPS:
                block = data.get(group) or {}
                as_of = as_of or block.get("timestamp")
                groups.setdefault(group, {})[kind] = [
                    _mover(r.get("symbol", ""), r.get("ltp"), r.get("prev_price"), r.get("perChange"), r.get("trade_quantity"))
                    for r in (block.get("data") or [])[:10]
                ]
    stamp = _nse_time(as_of)
    if not stamp:
        raise ValueError("variations without a timestamp")
    return {"asOf": stamp.isoformat(), "groups": groups}


async def _nse_pre_open() -> dict:
    """Pre-open movers by indicative opening price (IEP), from NSE's ALL and F&O pre-open lists.
    Stocks with no discovered price yet (IEP or quantity 0) are left out."""
    lists, stamp = {}, None
    async with httpx.AsyncClient(timeout=15.0, headers=NSE_HEADERS) as client:
        for key in ("ALL", "FO"):
            resp = await client.get(f"{NSE_API}/market-data-pre-open?key={key}")
            resp.raise_for_status()
            data = resp.json()
            stamp = stamp or _nse_time(data.get("timestamp"))
            lists[key] = [
                _mover(md["symbol"], md.get("iep"), md.get("previousClose"), md.get("pChange"), md.get("finalQuantity"))
                for md in ((item.get("metadata") or {}) for item in data.get("data") or [])
                if md.get("symbol") and float(md.get("iep") or 0) > 0 and float(md.get("previousClose") or 0) > 0
                and float(md.get("finalQuantity") or 0) > 0
            ]
    if not stamp or stamp.date() != get_ist_now().date():
        raise ValueError("no pre-open session today yet")  # before 09:00 the list is yesterday's
    return {"asOf": stamp.isoformat(), "groups": rank_groups(lists["ALL"], lists["FO"], await _group_members())}


async def _dhan_total_market() -> dict:
    """All NIFTY (Nifty Total Market) ranked from one batched Dhan quote for every member.
    After the close Dhan's last price is NSE's official closing price. The previous close is Dhan's
    during the session (the exchange's base price); otherwise the bhavcopy's: the latest one's close,
    or its previous close once it is the quote's own session."""
    from routers import dhan_market as dm
    from routers.stocks import _index_members, _latest_bhav_prices

    members = await _index_members(_GROUP_INDEX_CSV["TotalMarket"])
    instruments = await get_instruments()
    sids = {m["symbol"]: e["nse"]["sid"] for m in members if (e := instruments.get(m["symbol"])) and e["nse"]}
    async with dm._dhan_slot("/marketfeed/quote"):
        resp = await dm._dhan_post("/marketfeed/quote", {"NSE_EQ": [int(sid) for sid in sids.values()]})
    quotes = (resp.get("data") or {}).get("NSE_EQ") or {}
    bhav_day, bhav = await _latest_bhav_prices()
    live = market_phase() == "open"
    rows, latest = [], None
    for symbol, sid in sids.items():
        q = quotes.get(str(sid)) or {}
        price, traded = float(q.get("last_price") or 0), _dhan_time(q.get("last_trade_time"))
        if price <= 0 or not traded:
            continue
        close, prev = bhav.get(symbol, (None, None))
        base = float((q.get("ohlc") or {}).get("close") or 0) if live else 0.0
        base = base or (prev if bhav_day == traded.date().isoformat() else close)
        if not base:
            continue
        rows.append(_mover(symbol, price, base, (price - base) / base * 100, q.get("volume")))
        latest = max(latest, traded) if latest else traded
    if not rows:
        raise ValueError("no Total Market quotes")
    return {"asOf": latest.isoformat(), "groups": {"TotalMarket": rank_groups(rows, None, {"TotalMarket": set(sids)})["TotalMarket"]}}


def _dhan_time(text: Optional[str]) -> Optional[datetime]:
    """Dhan's "23/10/2026 15:59:04" (IST) as an aware datetime."""
    try:
        return datetime.strptime(str(text), "%d/%m/%Y %H:%M:%S").replace(tzinfo=IST)
    except ValueError:
        return None


async def _bhavcopy_snapshot() -> dict:
    """Last resort: the latest session's movers from the NSE bhavcopy (no F&O group)."""
    from routers.stocks import _latest_bhav_prices

    day, prices = await _latest_bhav_prices()
    rows = [_mover(s, c, p, (c - p) / p * 100, 0) for s, (c, p) in prices.items() if c and p]
    as_of = datetime.fromisoformat(day).replace(hour=15, minute=30, tzinfo=IST).isoformat() if day else None
    return {"asOf": as_of, "groups": rank_groups(rows, None, await _group_members())}


async def _shared(key: str, fetch, fresh: int) -> Optional[dict]:
    """One copy in Redis for every user, refreshed at most every `fresh` seconds. If the source fails,
    the last good copy is served and the source is asked again in a minute."""
    cached = await cache_get_json(key)
    if cached and time.time() - cached["at"] < fresh:
        return cached["data"]
    async with _movers_locks.setdefault(key, asyncio.Lock()):
        cached = await cache_get_json(key)  # another request may have refreshed it meanwhile
        if cached and time.time() - cached["at"] < fresh:
            return cached["data"]
        try:
            data = await fetch()
        except Exception as exc:
            logger.warning("%s refresh failed: %s", key, exc)
            data = None
        if data:
            await cache_set_json(key, {"at": time.time(), "data": data}, MOVERS_KEEP)
            return data
        if cached:
            await cache_set_json(key, {"at": time.time() - fresh + 60, "data": cached["data"]}, MOVERS_KEEP)
            return cached["data"]
        return None


async def market_movers(group: str = "NIFTY") -> dict:
    """Top 10 gainers and losers of one NSE group, with the market phase they belong to.
    - pre_open: NSE's indicative opening prices for today.
    - open / closing: NSE's session lists (closing: NSE's final prices land at 16:00).
    - closed: the last session's final lists, as NSE published them.
    A list from an earlier session is always labelled closed, whatever the clock says."""
    phase = market_phase()
    fresh = MOVERS_FRESH_CLOSED if phase == "closed" else MOVERS_FRESH_LIVE
    snapshot = await _shared("movers:preopen", _nse_pre_open, MOVERS_FRESH_LIVE) if phase == "pre_open" else None
    if snapshot is None and group == "TotalMarket" and phase != "pre_open":
        snapshot = await _shared("movers:totalmarket", _dhan_total_market, fresh)
    if snapshot is None:
        snapshot = await _shared("movers:variations", _nse_variations, fresh)
        if phase == "pre_open":
            phase = "closed"  # no pre-open list: yesterday's final lists, labelled as such
    if snapshot is None:
        try:
            snapshot = await _bhavcopy_snapshot()
        except Exception as exc:
            logger.warning("bhavcopy movers failed: %s", exc)
            snapshot = {"asOf": None, "groups": {}}
    stamp = datetime.fromisoformat(snapshot["asOf"]) if snapshot.get("asOf") else None
    if phase in ("open", "closing") and (not stamp or stamp.date() != get_ist_now().date()):
        phase = "closed"
    elif phase == "closing" and stamp and stamp.time() >= dtime(16, 0):
        phase = "closed"  # NSE's final values are in
    lists = snapshot["groups"].get(group) or {"gainers": [], "losers": []}
    return {"group": group, "label": MOVER_GROUPS.get(group, group), "phase": phase, "asOf": snapshot.get("asOf"),
            "gainers": lists.get("gainers", []), "losers": lists.get("losers", [])}


async def _with_names(items: list[dict]) -> list[dict]:
    """Company names for the dashboard list, from the in-memory instrument list."""
    instruments = await get_instruments()
    return [{**m, "name": (instruments.get(m["symbol"]) or {}).get("name", "")} for m in items]


@router.get("/movers")
async def get_movers(group: str = "NIFTY"):
    """Top gainers and losers for one group, with the market phase (see market_movers). An unknown or
    retired group (such as a remembered "Above ₹20") gets NIFTY 50, and says so in `group`."""
    if group not in MOVER_GROUPS:
        group = "NIFTY"
    movers = await market_movers(group)
    return {**movers, "groups": [{"key": k, "label": v} for k, v in MOVER_GROUPS.items()],
            "gainers": await _with_names(movers["gainers"]), "losers": await _with_names(movers["losers"])}


@router.get("/top-stocks")
async def get_top_stocks():
    """Top 10 NIFTY 50 gainers (the same lists as /movers; kept for the mobile app and the assistant)."""
    return {"gainers": await _with_names((await market_movers("NIFTY"))["gainers"])}


@router.get("/top-losers")
async def get_top_losers():
    """Top 10 NIFTY 50 losers (the same lists as /movers)."""
    return {"losers": await _with_names((await market_movers("NIFTY"))["losers"])}


def downsample(points: list[float], n: int = SPARK_POINTS) -> list[float]:
    """At most n evenly spaced points, always keeping the last one (the latest price)."""
    if len(points) <= n:
        return points
    step = (len(points) - 1) / (n - 1)
    return [points[round(i * step)] for i in range(n)]


async def _nse_spark(symbol: str) -> list[float]:
    """The day's price line for one stock from NSE's 1-minute chart, normal market only (no pre-open)."""
    url = f"{NSE_API}/NextApi/apiClient/GetQuoteApi?functionName=getSymbolChartData&symbol={quote(symbol)}EQN&days=1D"
    async with _spark_gate, httpx.AsyncClient(timeout=10.0, headers=NSE_HEADERS) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return downsample([float(p[1]) for p in resp.json().get("grapthData") or [] if len(p) > 2 and p[2] == "NM"])


@router.get("/sparklines")
async def get_sparklines(symbols: str):
    """Intraday price lines for up to 30 symbols, one shared copy per symbol: about a minute old while
    the market is open, kept until the next session once it closes."""
    wanted = [s.strip().upper() for s in symbols.split(",") if s.strip()][:30]
    ttl = 21600 if market_phase() == "closed" else 60
    out: dict[str, list[float]] = {}
    for symbol, cached in zip(wanted, await cache_get_many([f"spark:{s}" for s in wanted])):
        if cached is not None:
            out[symbol] = cached

    async def fill(symbol: str) -> None:
        try:
            out[symbol] = await _nse_spark(symbol)
        except Exception as exc:
            logger.warning("sparkline %s failed: %s", symbol, exc)
            out[symbol] = []
        await cache_set_json(f"spark:{symbol}", out[symbol], ttl if out[symbol] else 300)

    await asyncio.gather(*(fill(s) for s in wanted if s not in out))
    return {"sparklines": out}
