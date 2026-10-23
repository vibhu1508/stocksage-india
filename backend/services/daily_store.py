"""
Daily candles for every instrument, kept on the server's disk (SQLite), so daily charts, the
screener, indicators and previous closes don't depend on the provider answering at view time.

- One row per instrument and trading day: (segment, security id, day) -> OHLCV and its source.
  `day` is the epoch of IST midnight, the same stamp Dhan's daily candles carry.
- Filled lazily on read, at most once per session per instrument (`checked` table), from:
  Dhan on the instrument's own listing -> Dhan on its other listing (same ISIN) -> NSE's history.
  Dhan's daily history is adjusted for splits and bonuses; NSE's is raw, so its rows are marked.
- If a refetch disagrees with what we stored, a corporate action happened: the whole history is
  replaced with the provider's adjusted one.
- The evening job (scripts/daily_topup.py) adds each day from the NSE bhavcopy for NSE stocks
  already stored; indices and BSE-only stocks stay lazy.
"""

import asyncio
import logging
import os
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from fastapi import HTTPException

from utils.market_utils import IST, get_latest_market_date

logger = logging.getLogger("services.daily_store")

DB_PATH = Path(os.getenv("STOCKSAGE_DATA_DIR", str(Path.home() / "stocksage-data"))) / "daily.sqlite"
HISTORY_START = date(2000, 1, 1)
NSE_WINDOW_DAYS = 90         # NSE's history endpoints silently keep only the latest ~70 rows per call
NSE_FALLBACK_DAYS = 400      # on a view, enough for the 200-day average and a 1-year chart
SPLIT_TOLERANCE = 0.01       # a stored close off by >1% from the provider's means history was adjusted
RETRY_SECONDS = 1800         # the provider publishes a day's candle the next morning: re-check, gently

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    seg TEXT NOT NULL, sid TEXT NOT NULL, day INTEGER NOT NULL,
    o REAL NOT NULL, h REAL NOT NULL, l REAL NOT NULL, c REAL NOT NULL, v INTEGER NOT NULL DEFAULT 0,
    src TEXT NOT NULL,
    PRIMARY KEY (seg, sid, day)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS checked (
    seg TEXT NOT NULL, sid TEXT NOT NULL, session TEXT NOT NULL, at REAL NOT NULL,
    PRIMARY KEY (seg, sid)
) WITHOUT ROWID;
"""


def day_stamp(d: date) -> int:
    """IST midnight of a trading day, as epoch seconds (Dhan's daily candle time)."""
    return int(datetime(d.year, d.month, d.day, tzinfo=IST).timestamp())


def _connect() -> sqlite3.Connection:
    # A fresh connection per call: calls run in worker threads, and SQLite connections are per-thread.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")  # the API reads while the evening job writes
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(_SCHEMA)
    return conn


def upsert(seg: str, sid: str, rows: Iterable[tuple], src: str) -> int:
    """rows: (day, open, high, low, close, volume). Re-inserting the same day overwrites it."""
    rows = [(seg, str(sid), int(d), float(o), float(h), float(l), float(c), int(v or 0), src) for d, o, h, l, c, v in rows]
    with _connect() as conn:
        conn.executemany("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def replace_all(seg: str, sid: str, rows: Iterable[tuple], src: str) -> int:
    with _connect() as conn:
        conn.execute("DELETE FROM candles WHERE seg=? AND sid=?", (seg, str(sid)))
    return upsert(seg, sid, rows, src)


def read(seg: str, sid: str, from_day: Optional[int] = None, to_day: Optional[int] = None) -> list[tuple]:
    with _connect() as conn:
        return conn.execute(
            "SELECT day, o, h, l, c, v FROM candles WHERE seg=? AND sid=? AND day>=? AND day<=? ORDER BY day",
            (seg, str(sid), from_day or 0, to_day or 2**62),
        ).fetchall()


def checked(seg: str, sid: str) -> tuple[str, float]:
    """(last session known complete, when the providers were last asked)."""
    with _connect() as conn:
        row = conn.execute("SELECT session, at FROM checked WHERE seg=? AND sid=?", (seg, str(sid))).fetchone()
    return (row[0], row[1]) if row else ("", 0.0)


def mark_checked(seg: str, sid: str, session: str) -> None:
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO checked VALUES (?,?,?,?)", (seg, str(sid), session, time.time()))


def clear_checked(seg: str, sid: str) -> None:
    """Forget the instrument's last check, so its next read asks the provider again."""
    with _connect() as conn:
        conn.execute("DELETE FROM checked WHERE seg=? AND sid=?", (seg, str(sid)))


def latest_closes(seg: str) -> dict[str, tuple[int, float]]:
    """{sid: (last stored day, its close)} for every stored instrument of a segment."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT sid, day, c FROM candles WHERE seg=? AND (sid, day) IN "
            "(SELECT sid, MAX(day) FROM candles WHERE seg=? GROUP BY sid)", (seg, seg)).fetchall()
    return {sid: (day, c) for sid, day, c in rows}


def is_partial(seg: str, sid: str) -> bool:
    """True when nothing stored came from the primary provider: only the NSE fallback's last ~400
    days (raw, and limited to the listing's current series) or bhavcopy days on top of them."""
    with _connect() as conn:
        return conn.execute("SELECT 1 FROM candles WHERE seg=? AND sid=? AND src LIKE 'dhan%' LIMIT 1",
                            (seg, str(sid))).fetchone() is None


def needs_refill(stored: list[tuple], fetched: list[tuple]) -> bool:
    """True when a day we hold closes differently in the provider's data: a split or bonus adjusted it."""
    mine = {d: c for d, _, _, _, c, _ in stored}
    for d, _, _, _, c, _ in fetched:
        if d in mine and mine[d] and abs(c - mine[d]) / mine[d] > SPLIT_TOLERANCE:
            return True
    return False


# ----- sources -------------------------------------------------------------------------------

def _dhan_rows(data: dict) -> list[tuple]:
    cols = [data.get(k) or [] for k in ("timestamp", "open", "high", "low", "close", "volume")]
    if not cols[0]:
        return []
    cols[5] = cols[5] or [0] * len(cols[0])
    return [(int(t), o, h, l, c, v) for t, o, h, l, c, v in zip(*cols) if None not in (t, o, h, l, c)]


async def _from_dhan(seg: str, sid: str, instrument: str, start: date, end: date) -> list[tuple]:
    from routers import dhan_market as dm  # the provider client lives in the router module

    payload = {"securityId": str(sid), "exchangeSegment": seg, "instrument": instrument, "expiryCode": 0,
               "oi": False, "fromDate": start.isoformat(), "toDate": (end + timedelta(days=1)).isoformat()}
    resp = await dm._cached_dhan_post("/charts/historical", payload, "history")
    return _dhan_rows(resp.get("data") or {})


def _nse_date(text: str) -> date:
    return datetime.strptime(text.title(), "%d-%b-%Y").date()


def nse_equity_rows(data: list[dict], series: str) -> list[tuple]:
    """NSE security history -> rows, keeping only the listing's own series (block deals and other
    series share the symbol but carry other prices)."""
    return [(day_stamp(_nse_date(r["mTIMESTAMP"])), r["CH_OPENING_PRICE"], r["CH_TRADE_HIGH_PRICE"],
             r["CH_TRADE_LOW_PRICE"], r["CH_CLOSING_PRICE"], r.get("CH_TOT_TRADED_QTY") or 0)
            for r in data if r.get("CH_SERIES") == series]


def nse_index_rows(data: list[dict]) -> list[tuple]:
    return [(day_stamp(_nse_date(r["EOD_TIMESTAMP"])), r["EOD_OPEN_INDEX_VAL"], r["EOD_HIGH_INDEX_VAL"],
             r["EOD_LOW_INDEX_VAL"], r["EOD_CLOSE_INDEX_VAL"], r.get("HIT_TRADED_QTY") or 0) for r in data]


async def _from_nse(entry: dict, index_name: Optional[str], start: date, end: date) -> list[tuple]:
    """NSE's own daily history in 90-day windows (raw prices, not split-adjusted)."""
    import urllib.parse
    from routers.strategy_builder import nse_session

    rows: list[tuple] = []
    window_start = start
    while window_start <= end:
        window_end = min(end, window_start + timedelta(days=NSE_WINDOW_DAYS))
        span = f"from={window_start:%d-%m-%Y}&to={window_end:%d-%m-%Y}"
        if index_name:
            url = f"https://www.nseindia.com/api/historicalOR/indicesHistory?indexType={urllib.parse.quote(index_name)}&{span}"
            rows += nse_index_rows((await nse_session.get_data(url)).get("data") or [])
        else:
            nse = entry["nse"]
            url = (f"https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData?{span}"
                   f"&symbol={urllib.parse.quote(nse['symbol'])}&type=priceVolumeDeliverable&series=ALL")
            rows += nse_equity_rows((await nse_session.get_data(url)).get("data") or [], nse.get("series") or "EQ")
        window_start = window_end + timedelta(days=1)
        await asyncio.sleep(0.5)  # NSE is a shared, unofficial source: keep the pace gentle
    return sorted({r[0]: r for r in rows}.values())


def _listing(entry: dict, seg: str) -> Optional[dict]:
    return entry["nse"] if seg == "NSE_EQ" else entry["bse"]


async def fetch(identity: dict, start: date, end: date) -> tuple[list[tuple], str]:
    """Daily candles from the first source that answers: (rows, source). Raises if none does."""
    from routers.stocks import INDEX_CONSTITUENTS
    from services.instruments import get_indices, get_instruments

    seg, sid, instrument = identity["exchangeSegment"], str(identity["securityId"]), identity["instrument"]
    errors = []
    try:
        return await _from_dhan(seg, sid, instrument, start, end), "dhan"
    except HTTPException as exc:
        errors.append(f"dhan {seg}: {exc.detail}")

    entry, index_name = None, None
    if seg == "IDX_I":
        index = next((i for i in (await get_indices()).values() if i["sid"] == sid), None)
        if index and index["exchange"] == "NSE":
            index_name = INDEX_CONSTITUENTS.get(index["symbol"], (index["name"].upper(),))[0]
    elif seg in ("NSE_EQ", "BSE_EQ"):
        entry = next((e for e in (await get_instruments()).values() if (l := _listing(e, seg)) and l["sid"] == sid), None)
        other = entry and _listing(entry, "BSE_EQ" if seg == "NSE_EQ" else "NSE_EQ")
        if other:  # the same company on its other exchange: Dhan sometimes has one and not the other
            other_seg = "BSE_EQ" if seg == "NSE_EQ" else "NSE_EQ"
            try:
                return await _from_dhan(other_seg, other["sid"], "EQUITY", start, end), f"dhan-{other_seg}"
            except HTTPException as exc:
                errors.append(f"dhan {other_seg}: {exc.detail}")

    if index_name or (entry and entry["nse"]):
        nse_start = max(start, end - timedelta(days=NSE_FALLBACK_DAYS))
        try:
            rows = await _from_nse(entry, index_name, nse_start, end)
            if rows:
                return rows, "nse"
            errors.append("nse: no rows")
        except Exception as exc:  # an unofficial endpoint: any failure just ends the chain
            errors.append(f"nse: {type(exc).__name__}")
    logger.warning("daily candles unavailable for %s:%s (%s)", seg, sid, "; ".join(errors))
    raise HTTPException(status_code=502, detail="Daily candles unavailable")


# ----- the read path -------------------------------------------------------------------------

_fill_locks: dict[tuple, asyncio.Lock] = {}


async def daily_rows(identity: dict) -> list[tuple]:
    """All stored daily candles for an instrument, first bringing them up to the latest session.
    Each instrument is refreshed from a provider at most once per session; if the providers fail,
    what is stored is served (a provider outage then costs freshness, not the chart)."""
    seg, sid = identity["exchangeSegment"], str(identity["securityId"])
    session = get_latest_market_date(datetime.now(IST)).isoformat()
    lock = _fill_locks.setdefault((seg, sid), asyncio.Lock())
    async with lock:
        stored = await asyncio.to_thread(read, seg, sid)
        done, asked_at = await asyncio.to_thread(checked, seg, sid)
        # Fallback-only history stays incomplete until the primary provider answers with the full one.
        partial = bool(stored) and await asyncio.to_thread(is_partial, seg, sid)
        if stored and ((done == session and not partial) or time.time() - asked_at < RETRY_SECONDS):
            return stored
        start = HISTORY_START if not stored or partial else datetime.fromtimestamp(stored[-1][0], IST).date() - timedelta(days=10)
        try:
            rows, src = await fetch(identity, start, date.fromisoformat(session))
        except HTTPException:
            if stored:
                await asyncio.to_thread(mark_checked, seg, sid, done)  # wait RETRY_SECONDS before asking again
                return stored
            raise
        if partial and src.startswith("dhan"):
            logger.info("full history for %s:%s from %s replaces the fallback's", seg, sid, src)
            await asyncio.to_thread(replace_all, seg, sid, rows, src)
        elif stored and needs_refill(stored, rows):
            logger.warning("history of %s:%s changed (split or bonus); refetching all", seg, sid)
            try:
                rows, src = await fetch(identity, HISTORY_START, date.fromisoformat(session))
            except HTTPException:
                return stored  # keep serving; the next session's check retries the refetch
            await asyncio.to_thread(replace_all, seg, sid, rows, src)
        else:
            await asyncio.to_thread(upsert, seg, sid, rows, src)
        latest = await asyncio.to_thread(read, seg, sid)
        # Complete only once the session's own candle is in; until then retry every RETRY_SECONDS
        # (illiquid stocks with no trade that day simply keep that gentle retry).
        has_session = bool(latest) and latest[-1][0] >= day_stamp(date.fromisoformat(session))
        complete = has_session and src.startswith("dhan")
        await asyncio.to_thread(mark_checked, seg, sid, session if complete else done)
        return latest


def as_chart_candles(rows: list[tuple]) -> list[dict]:
    return [{"time": d, "open": round(o, 4), "high": round(h, 4), "low": round(l, 4), "close": round(c, 4)} for d, o, h, l, c, _ in rows]
