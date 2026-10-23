"""
Every listed company and ETF on NSE and BSE, one entry per company, from Dhan's detailed
instrument list (it carries ISINs; the compact list the chart code uses does not).

Keys: the NSE symbol for anything on NSE; the BSE symbol for BSE-only companies, or
"BSE:<symbol>" when that symbol belongs to a different NSE company (7 such clashes today).
No dots in keys: the site's rewrite rule treats dotted paths as files.
"""

import asyncio
import csv
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Iterable, Optional

import httpx

logger = logging.getLogger("services.instruments")

DETAILED_MASTER_URL = os.getenv("DHAN_DETAILED_MASTER_URL", "https://images.dhan.co/api-data/api-scrip-master-detailed.csv")
LOCAL_PATH = Path(tempfile.gettempdir()) / "stocksage" / "dhan_api_scrip_master_detailed.csv"
REFRESH_SECONDS = 86400
# The parsed list (~2 MB), so a restarted process is ready in well under a second instead of
# downloading and parsing the 36 MB file (5.6 s + 3.9 s measured) before the first search answers.
PARSED_PATH = Path(os.getenv("STOCKSAGE_DATA_DIR", str(Path.home() / "stocksage-data"))) / "instruments.json"

_cache: dict[str, dict] = {}
_indices: dict[str, dict] = {}
_loaded_at = 0.0
_lock = asyncio.Lock()
_refreshing: Optional[asyncio.Task] = None  # held so the background refresh isn't garbage-collected


def _is_company_or_etf(row: dict) -> bool:
    if row.get("SEGMENT") != "E":
        return False
    isin = (row.get("ISIN") or "").strip()
    kind = row.get("INSTRUMENT_TYPE")
    # ISIN: IN + E (company) + 4 issuer + 2 security type + ...; type 01 is equity shares (02+ are debt etc.).
    return (kind == "ES" and isin.startswith("INE") and isin[7:9] == "01") or (kind == "ETF" and len(isin) == 12)


def build_instruments(rows: Iterable[dict]) -> dict[str, dict]:
    """Rows of Dhan's detailed list -> {key: {symbol, name, isin, kind, nse, bse}}."""
    by_isin: dict[str, dict] = {}
    for row in rows:
        if not _is_company_or_etf(row):
            continue
        exch = row.get("EXCH_ID")
        if exch not in ("NSE", "BSE"):
            continue
        entry = by_isin.setdefault(row["ISIN"].strip(), {"nse": None, "bse": None, "name": "", "kind": row["INSTRUMENT_TYPE"]})
        listing = {"sid": row["SECURITY_ID"].strip(), "symbol": row["UNDERLYING_SYMBOL"].strip(), "series": row.get("SERIES") or ""}
        if entry[exch.lower()] is None:  # a company has one listing per exchange; keep the first
            entry[exch.lower()] = listing
            if exch == "NSE" or not entry["name"]:
                entry["name"] = (row.get("DISPLAY_NAME") or row.get("SYMBOL_NAME") or "").strip()

    nse_symbols = {e["nse"]["symbol"] for e in by_isin.values() if e["nse"]}
    out: dict[str, dict] = {}
    for isin, e in by_isin.items():
        if e["nse"]:
            key = symbol = e["nse"]["symbol"]
        else:
            symbol = e["bse"]["symbol"]
            key = f"BSE:{symbol}" if symbol in nse_symbols else symbol
        if key and key not in out:
            out[key] = {"symbol": symbol, "name": e["name"], "isin": isin, "kind": e["kind"], "nse": e["nse"], "bse": e["bse"]}
    return out


def build_indices(rows: Iterable[dict]) -> dict[str, dict]:
    """Index rows (segment I, NSE and BSE) -> {"INDEX:<symbol>": {symbol, name, exchange, sid}}.
    The prefix keeps an index apart from a stock with the same ticker."""
    out: dict[str, dict] = {}
    for row in rows:
        if row.get("SEGMENT") != "I" or row.get("EXCH_ID") not in ("NSE", "BSE"):
            continue
        symbol = row["UNDERLYING_SYMBOL"].strip().upper()
        out.setdefault(f"INDEX:{symbol}", {
            "symbol": symbol, "name": (row.get("DISPLAY_NAME") or symbol).strip(),
            "exchange": row["EXCH_ID"], "sid": row["SECURITY_ID"].strip(),
        })
    return out


def _parse_file(path: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    with path.open(newline="", encoding="utf-8") as f:
        # Only equity and index rows are used (~25k of ~210k), so hold just those.
        rows = [r for r in csv.DictReader(f) if r.get("SEGMENT") in ("E", "I")]
    return build_instruments(rows), build_indices(rows)


async def _download() -> None:
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    partial = LOCAL_PATH.with_name(f"{LOCAL_PATH.name}.{os.getpid()}.part")  # the API and market service may both refresh
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("GET", DETAILED_MASTER_URL) as resp:
            resp.raise_for_status()
            with partial.open("wb") as f:  # streamed to disk: the file is ~36 MB
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
    partial.replace(LOCAL_PATH)


def _load_parsed() -> Optional[tuple[dict, dict, float]]:
    try:
        saved = json.loads(PARSED_PATH.read_text())
        return saved["companies"], saved["indices"], saved["built"]
    except (OSError, ValueError, KeyError):
        return None


def _save_parsed(companies: dict, indices: dict, built: float) -> None:
    PARSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    partial = PARSED_PATH.with_name(f"{PARSED_PATH.name}.{os.getpid()}.part")
    partial.write_text(json.dumps({"companies": companies, "indices": indices, "built": built}))
    partial.replace(PARSED_PATH)


async def _refresh() -> None:
    """Download and parse the provider's list, then swap it in. Failures keep the current list."""
    global _cache, _indices, _loaded_at
    try:
        await _download()
    except Exception as exc:
        logger.warning("instrument list download failed (%s); using the saved copy", exc)
    try:
        if not LOCAL_PATH.exists():
            raise FileNotFoundError(LOCAL_PATH)
        # Parsing ~200k rows takes a few seconds; keep it off the event loop.
        companies, indices = await asyncio.to_thread(_parse_file, LOCAL_PATH)
        _cache, _indices, _loaded_at = companies, indices, time.time()
        await asyncio.to_thread(_save_parsed, companies, indices, _loaded_at)
        logger.info("instrument list: %d companies and ETFs, %d indices", len(_cache), len(_indices))
    except Exception as exc:
        logger.warning("instrument list refresh failed: %s", exc)
        _loaded_at = time.time() - REFRESH_SECONDS + 600  # retry in 10 minutes, not on every request


async def get_instruments() -> dict[str, dict]:
    """The company list. Requests never wait on the daily download: a new process loads the saved
    parsed copy, and refreshes run in the background while the current list keeps answering."""
    global _cache, _indices, _loaded_at, _refreshing
    if not _cache:
        async with _lock:
            if not _cache:
                saved = await asyncio.to_thread(_load_parsed)
                if saved:
                    _cache, _indices, _loaded_at = saved
                else:
                    await _refresh()  # first run on this machine: nothing saved yet
    if time.time() - _loaded_at >= REFRESH_SECONDS and (_refreshing is None or _refreshing.done()):
        _refreshing = asyncio.create_task(_refresh())
    return _cache


async def get_indices() -> dict[str, dict]:
    """NSE and BSE indices, loaded and refreshed with the company list."""
    await get_instruments()
    return _indices
