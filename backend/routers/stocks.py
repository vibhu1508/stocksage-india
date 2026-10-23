"""
Stock Comparison Router - BhavCopy download and stock price comparison
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any, Literal
import asyncio
import csv
import logging
import pandas as pd
import httpx
import zipfile
import io
import time

from database import get_db
from routers.auth import get_current_user
from models import User
from routers.strategy_builder import nse_session
from services import bhavcopy_archive
from services.instruments import get_indices, get_instruments
from services.redis_store import _key as rkey, get_redis_client
from utils.market_utils import IST

router = APIRouter()
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date}_F_0000.csv.zip"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/zip",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}
POLITE_DELAY = 1.5


def download_bhavcopy(target_date: date) -> Optional[pd.DataFrame]:
    """
    Downloads the NSE BhavCopy for a specific date and returns as DataFrame.
    Optimized for memory usage.
    """
    try:
        content = bhavcopy_archive.get_zip("cm", BASE_URL, target_date)
        if content is None:
            return None

        # Extract CSV from zip
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            csv_filename = z.namelist()[0]
            with z.open(csv_filename) as f:
                # OPTIMIZATION: Only load necessary columns
                target_cols = ['TradDt', 'SctySrs', 'FinInstrmNm', 'ClsPric', 'PrvsClsgPric', 'TckrSymb', 'TtlTradgVol']
                
                # Check headers
                header_check = pd.read_csv(f, nrows=0)
                available_cols = [c for c in target_cols if c in header_check.columns]
                
                f.seek(0)
                df = pd.read_csv(f, usecols=available_cols)
        
        # OPTIMIZATION: Filter early to reduce memory before processing
        if 'SctySrs' in df.columns:
            df = df[df['SctySrs'].isin(['EQ', 'BE'])].copy()
        
        # OPTIMIZATION: Downcast numeric types
        for col in ['ClsPric', 'PrvsClsgPric', 'TtlTradgVol']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').astype('float32')
        
        # Drop rows with missing essential data
        df.dropna(subset=['ClsPric', 'TtlTradgVol'], inplace=True)
        
        return df
        
    except Exception as e:
        print(f"Error downloading BhavCopy for {target_date}: {e}")
        return None


def calculate_percentage_change(df1: pd.DataFrame, df2: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate percentage change in closing price between two DataFrames.
    Matches logic from stock_comparison_tab.py (lines 88-122)
    """
    # Merge on BOTH TckrSymb AND FinInstrmNm to avoid duplicates (like Streamlit line 95)
    merged = pd.merge(
        df1[['TckrSymb', 'FinInstrmNm', 'ClsPric', 'TtlTradgVol']],
        df2[['TckrSymb', 'FinInstrmNm', 'ClsPric', 'TtlTradgVol']],
        on=['TckrSymb', 'FinInstrmNm'],
        suffixes=('_old', '_new')
    )
    
    # Handle division by zero for price change (like Streamlit line 98)
    merged['ClsPric_old'] = merged['ClsPric_old'].replace(0, pd.NA)
    merged['PctChange'] = ((merged['ClsPric_new'] - merged['ClsPric_old']) / merged['ClsPric_old'] * 100)
    
    # Handle division by zero for volume ratio (like Streamlit lines 101-102)
    merged['TtlTradgVol_old'] = merged['TtlTradgVol_old'].replace(0, pd.NA)
    merged['VolumeRatio'] = merged['TtlTradgVol_new'] / merged['TtlTradgVol_old']
    
    # Drop rows with NaN in calculated columns
    merged.dropna(subset=['PctChange', 'VolumeRatio'], inplace=True)
    
    # Round values for cleaner display
    merged['PctChange'] = merged['PctChange'].round(2)
    merged['VolumeRatio'] = merged['VolumeRatio'].round(2)
    
    # Rename columns for API response (matching Streamlit line 114-120)
    merged = merged.rename(columns={
        'TckrSymb': 'Symbol',
        'FinInstrmNm': 'InstrumentName',
        'ClsPric_old': 'OldPrice',
        'ClsPric_new': 'NewPrice',
        'TtlTradgVol_new': 'Volume'
    })
    
    # Select relevant columns and sort by percentage change
    result = merged[['Symbol', 'InstrumentName', 'OldPrice', 'NewPrice', 'PctChange', 'VolumeRatio', 'Volume']]
    return result.sort_values('PctChange', ascending=False)


@router.get("/symbols")
async def get_symbols(current_user: User = Depends(get_current_user)):
    """Get list of available stock symbols"""
    try:
        # Try to read from SYMBOLS.csv
        symbols_df = pd.read_csv('SYMBOLS.csv')
        return {"symbols": symbols_df['TckrSymb'].tolist()}
    except FileNotFoundError:
        # Fallback to downloading latest BhavCopy
        today = date.today()
        df = download_bhavcopy(today)
        if df is not None and 'TckrSymb' in df.columns:
            return {"symbols": df['TckrSymb'].unique().tolist()}
        return {"symbols": []}

_nse_search_cache: Dict[str, dict] = {}
_nse_search_cache_ttl = timedelta(seconds=30)
_nse_client: Optional[httpx.AsyncClient] = None
_nse_client_lock = asyncio.Lock()
_nse_bootstrap_at: Optional[datetime] = None
_nse_bootstrap_ttl = timedelta(minutes=10)

_known_index_symbols = {
    "NIFTY",
    "NIFTY 50",
    "BANKNIFTY",
    "BANK NIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
}


def _get_series_from_item(item: dict) -> str:
    candidates = [
        item.get("series"),
        item.get("mSeries"),
        item.get("instrument"),
        item.get("instrumentType"),
        item.get("assetType"),
        item.get("type"),
        item.get("segment"),
        item.get("metadata", {}).get("series") if isinstance(item.get("metadata"), dict) else None,
        item.get("metadata", {}).get("instrumentType") if isinstance(item.get("metadata"), dict) else None,
    ]
    for value in candidates:
        if value is None:
            continue
        parsed = str(value).strip()
        if parsed:
            return parsed.upper()
    return ""


def _allowed_instruments(symbol: str, name: str, series: str) -> List[str]:
    s = symbol.upper().strip()
    n = name.upper().strip()
    sr = series.upper().strip()

    is_index_like = s in _known_index_symbols or "INDEX" in n
    is_derivative_series = any(tag in sr for tag in ["FUT", "OPT", "FNO", "DERIV", "IDX"])
    is_equity_series = sr in {"EQ", "BE", "SM", "ST"}

    if is_index_like or is_derivative_series:
        if "OPT" in sr:
            return ["OPTION"]
        if "FUT" in sr:
            return ["FUTURE"]
        return ["FUTURE", "OPTION"]

    if is_equity_series:
        return ["EQUITY"]

    return ["EQUITY", "FUTURE", "OPTION"]


def _squash(text: str) -> str:
    return text.replace(" ", "").upper()


_search_index: tuple = (None, None, [])  # (companies, indices, prepared rows) for the current lists


def _prepared(instruments: dict, indices: Optional[dict]) -> list[tuple]:
    """Space-free, upper-case match keys, built once per list instead of on every keystroke."""
    global _search_index
    if _search_index[0] is instruments and _search_index[1] is indices:
        return _search_index[2]
    rows = [
        (key, _squash(e["symbol"]), _squash(e["name"]), _squash(key), len(e["symbol"]), 1 if e["nse"] else 2,
         {"symbol": key, "name": e["name"], "exchanges": [x for x in ("NSE", "BSE") if e[x.lower()]]})
        for key, e in instruments.items()
    ] + [
        (key, _squash(e["symbol"]), _squash(e["name"]), _squash(key), len(e["symbol"]), 0,
         {"symbol": key, "name": e["name"], "exchanges": [e["exchange"]], "kind": "index"})
        for key, e in (indices or {}).items()
    ]
    _search_index = (instruments, indices, rows)
    return rows


def rank_search(instruments: dict, query: str, limit: int, indices: Optional[dict] = None) -> list[dict]:
    """Best matches first: exact symbol or name, symbol prefix, name prefix, then anywhere; spaces are
    ignored ("nifty50" finds Nifty 50). Ties: indices, then NSE-listed, then shorter symbols.
    `exchanges` drives the NSE/BSE badges; indices also carry kind "index"."""
    q = _squash(query)
    if not q:
        return []
    ranked = []
    for key, sym, nm, key_sq, sym_len, tie, result in _prepared(instruments, indices):
        if q in (sym, nm, key_sq):
            rank = 0
        elif sym.startswith(q):
            rank = 1
        elif nm.startswith(q):
            rank = 2
        elif q in sym:
            rank = 3
        elif q in nm:
            rank = 4
        else:
            continue
        ranked.append((rank, tie, sym_len, key, result))
    ranked.sort(key=lambda r: r[:4])
    return [r[4] for r in ranked[:limit]]


@router.get("/search")
async def search_symbols(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results to return"),
    current_user: User = Depends(get_current_user)
):
    """Autocomplete over every NSE and BSE company and ETF (SME and BSE-only included)."""
    results = rank_search(await get_instruments(), q, limit, await get_indices())
    return {"query": q, "count": len(results), "results": results}


@router.get("/isin-map")
async def isin_map(response: Response):
    """{symbol key: ISIN} for every NSE and BSE company and ETF, used to show company logos.
    Public and cached a day: it is the same for everyone and changes only with listings."""
    instruments = await get_instruments()
    if not instruments:
        raise HTTPException(status_code=503, detail="Company list is not available yet")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return {key: entry["isin"] for key, entry in instruments.items()}


@router.get("/nse-global-search")
async def nse_global_search(
    q: str = Query(..., min_length=2, description="Search query"),
    search_type: Literal["derivatives", "equity", "etf"] = Query(
        "equity",
        alias="type",
        description="NSE global search type",
    ),
    limit: int = Query(10, ge=1, le=25, description="Max results to return"),
    current_user: User = Depends(get_current_user),
):
    """Proxy NSE global search by type (derivatives/equity/etf) for frontend autocomplete."""
    query = q.strip()
    if len(query) < 2:
        return {"query": query, "count": 0, "results": [], "type": search_type}

    cache_key = f"{search_type}:{query.lower()}"
    now = datetime.utcnow()
    cached = _nse_search_cache.get(cache_key)
    if cached and cached.get("expires_at") and cached["expires_at"] > now:
        cached_results = cached.get("results", [])[:limit]
        return {
            "query": query,
            "count": len(cached_results),
            "results": cached_results,
            "type": search_type,
            "source": "cache",
        }

    client = await _get_nse_client()
    await _ensure_nse_bootstrap(client)

    endpoint_by_type = {
        "derivatives": "derivatives",
        "equity": "equity",
        "etf": "etf",
    }
    nse_type = endpoint_by_type.get(search_type, "equity")
    search_url = f"https://www.nseindia.com/api/NextApi/globalSearch/{nse_type}?symbol={query}"

    try:
        response = await client.get(search_url)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Unable to fetch symbol suggestions from NSE")

    raw_items = []
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            raw_items = payload.get("data", [])
        elif isinstance(payload.get("results"), list):
            raw_items = payload.get("results", [])
        elif isinstance(payload.get("symbols"), list):
            raw_items = payload.get("symbols", [])

    results = []
    seen = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        symbol = (
            item.get("symbol")
            or item.get("metadata", {}).get("symbol")
            or item.get("mSymbol")
            or item.get("searchString")
            or ""
        )
        name = (
            item.get("companyName")
            or item.get("name")
            or item.get("metadata", {}).get("companyName")
            or item.get("metadata", {}).get("symbol")
            or symbol
        )

        symbol = str(symbol).strip().upper()
        name = str(name).strip()
        if not symbol:
            continue

        key = f"{symbol}|{name}"
        if key in seen:
            continue
        seen.add(key)

        series = _get_series_from_item(item)
        allowed = _allowed_instruments(symbol, name, series)

        results.append(
            {
                "symbol": symbol,
                "name": name,
                "series": series,
                "allowed_instruments": allowed,
            }
        )
        if len(results) >= max(25, limit):
            break

    _nse_search_cache[cache_key] = {
        "results": results,
        "expires_at": datetime.utcnow() + _nse_search_cache_ttl,
    }

    trimmed = results[:limit]

    return {
        "query": query,
        "count": len(trimmed),
        "results": trimmed,
        "type": search_type,
        "source": "live",
    }


async def _get_nse_client() -> httpx.AsyncClient:
    global _nse_client
    if _nse_client is not None:
        return _nse_client

    async with _nse_client_lock:
        if _nse_client is None:
            _nse_client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=2.0, read=3.5, write=3.0, pool=3.0),
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.nseindia.com/",
                    "Origin": "https://www.nseindia.com",
                    "Connection": "keep-alive",
                },
                follow_redirects=True,
            )
    return _nse_client


async def _ensure_nse_bootstrap(client: httpx.AsyncClient) -> None:
    global _nse_bootstrap_at
    now = datetime.utcnow()
    if _nse_bootstrap_at and now - _nse_bootstrap_at < _nse_bootstrap_ttl:
        return

    try:
        await client.get("https://www.nseindia.com")
        _nse_bootstrap_at = now
    except httpx.HTTPError:
        # Keep endpoint functional even if cookie warmup fails.
        return


@router.get("/live-search")
async def live_search_stocks(
    symbols: str = Query(..., description="Comma-separated symbols to search"),
    date1: str = Query(..., description="First date (YYYY-MM-DD)"),
    date2: str = Query(..., description="Second date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user)
):
    """
    Search for specific stocks and compare their prices between two dates.
    """
    try:
        parsed_date1 = datetime.strptime(date1, "%Y-%m-%d").date()
        parsed_date2 = datetime.strptime(date2, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    # Download both BhavCopies
    df1 = download_bhavcopy(parsed_date1)
    df2 = download_bhavcopy(parsed_date2)
    
    if df1 is None:
        raise HTTPException(status_code=404, detail=f"No data available for {date1}")
    if df2 is None:
        raise HTTPException(status_code=404, detail=f"No data available for {date2}")
    
    # Parse symbols
    symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    
    if not symbol_list:
        raise HTTPException(status_code=400, detail="At least one symbol is required")
    
    # Calculate comparison
    comparison = calculate_percentage_change(df1, df2)
    
    # Filter by specified symbols
    filtered = comparison[comparison['Symbol'].isin(symbol_list)]
    
    # Check which symbols were not found
    found_symbols = filtered['Symbol'].tolist()
    not_found = [s for s in symbol_list if s not in found_symbols]
    
    return {
        "date1": date1,
        "date2": date2,
        "searched_symbols": symbol_list,
        "found_count": len(filtered),
        "not_found": not_found,
        "data": filtered.to_dict(orient='records')
    }


@router.get("/bhavcopy/{target_date}")
async def get_bhavcopy(
    target_date: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get BhavCopy data for a specific date.
    Date format: YYYY-MM-DD
    """
    try:
        parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    df = download_bhavcopy(parsed_date)
    
    if df is None:
        raise HTTPException(status_code=404, detail=f"No data available for {target_date}")
    
    # Select relevant columns and convert to dict
    columns = ['TckrSymb', 'OpnPric', 'HghPric', 'LwPric', 'ClsPric', 'TtlTrdVol', 'TtlTrdVal']
    available_cols = [c for c in columns if c in df.columns]
    
    return {
        "date": target_date,
        "count": len(df),
        "data": df[available_cols].to_dict(orient='records')
    }


@router.get("/compare")
async def compare_stocks(
    date1: str = Query(..., description="First date (YYYY-MM-DD)"),
    date2: str = Query(..., description="Second date (YYYY-MM-DD)"),
    symbols: Optional[str] = Query(None, description="Comma-separated symbols to filter"),
    current_user: User = Depends(get_current_user)
):
    """
    Compare stock prices between two dates.
    Returns percentage change for each stock.
    """
    try:
        parsed_date1 = datetime.strptime(date1, "%Y-%m-%d").date()
        parsed_date2 = datetime.strptime(date2, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    # Download both BhavCopies
    df1 = download_bhavcopy(parsed_date1)
    df2 = download_bhavcopy(parsed_date2)
    
    if df1 is None:
        raise HTTPException(status_code=404, detail=f"No data available for {date1}")
    if df2 is None:
        raise HTTPException(status_code=404, detail=f"No data available for {date2}")
    
    # Calculate comparison
    comparison = calculate_percentage_change(df1, df2)
    
    # Filter by symbols if provided
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(',')]
        comparison = comparison[comparison['Symbol'].isin(symbol_list)]
    
    return {
        "date1": date1,
        "date2": date2,
        "count": len(comparison),
        "gainers": comparison.head(10).to_dict(orient='records'),
        "losers": comparison.tail(10).to_dict(orient='records'),
        "data": comparison.to_dict(orient='records')
    }


# ---------------------------------------------------------------------------------------------
# Index analysis: NSE's index overview (level, breadth, valuation) and, for the indices NSE
# publishes a constituent list for, each member's day move from the latest bhavcopy.

# Dhan index symbol -> (NSE allIndices name, NSE archive constituents file ind_<file>list.csv).
INDEX_CONSTITUENTS = {
    "NIFTY": ("NIFTY 50", "nifty50"), "NIFTYNXT50": ("NIFTY NEXT 50", "niftynext50"),
    "NIFTY 100": ("NIFTY 100", "nifty100"), "NIFTY 200": ("NIFTY 200", "nifty200"), "NIFTY 500": ("NIFTY 500", "nifty500"),
    "BANKNIFTY": ("NIFTY BANK", "niftybank"), "FINNIFTY": ("NIFTY FINANCIAL SERVICES", "niftyfinance"),
    "NIFTYIT": ("NIFTY IT", "niftyit"), "NIFTY AUTO": ("NIFTY AUTO", "niftyauto"), "NIFTY PHARMA": ("NIFTY PHARMA", "niftypharma"),
    "NIFTY FMCG": ("NIFTY FMCG", "niftyfmcg"), "NIFTY METAL": ("NIFTY METAL", "niftymetal"), "NIFTY REALTY": ("NIFTY REALTY", "niftyrealty"),
    "NIFTY ENERGY": ("NIFTY ENERGY", "niftyenergy"), "NIFTY MEDIA": ("NIFTY MEDIA", "niftymedia"),
    "NIFTY PSU BANK": ("NIFTY PSU BANK", "niftypsubank"), "NIFTY PVT BANK": ("NIFTY PRIVATE BANK", "nifty_privatebank"),
    "NIFTYMCAP50": ("NIFTY MIDCAP 50", "niftymidcap50"), "NIFTY MID100 FREE": ("NIFTY MIDCAP 100", "niftymidcap100"),
    "NIFTY MIDCAP 150": ("NIFTY MIDCAP 150", "niftymidcap150"), "NIFTY SMALLCAP 100": ("NIFTY SMALLCAP 100", "niftysmallcap100"),
    "NIFTY SMALLCAP 250": ("NIFTY SMALLCAP 250", "niftysmallcap250"), "NIFTY HEALTHCARE": ("NIFTY HEALTHCARE INDEX", "niftyhealthcare"),
    "NIFTY CONSUMPTION": ("NIFTY INDIA CONSUMPTION", "niftyconsumption"), "NIFTYINFRA": ("NIFTY INFRASTRUCTURE", "niftyinfra"),
    "NIFTY COMMODITIES": ("NIFTY COMMODITIES", "niftycommodities"), "NIFTYCPSE": ("NIFTY CPSE", "niftycpse"),
    "NIFTYPSE": ("NIFTY PSE", "niftypse"), "NIFTY OIL AND GAS": ("NIFTY OIL & GAS", "niftyoilgas"),
}
_OVERVIEW_FIELDS = ("last", "variation", "percentChange", "open", "high", "low", "previousClose", "yearHigh", "yearLow",
                    "pe", "pb", "dy", "advances", "declines", "unchanged", "perChange30d", "perChange365d",
                    "oneWeekAgoVal", "oneMonthAgoVal", "oneYearAgoVal")
_all_indices_cache: dict = {"at": 0.0, "rows": []}
_members_cache: dict[str, tuple[float, list]] = {}
_bhav_cache: dict = {"at": 0.0, "date": None, "prices": {}}


def _number(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def constituent_moves(members: list[dict], prices: dict[str, tuple[float, float]]) -> dict:
    """Join an index's members with bhavcopy (close, previous close): each member's day move,
    biggest movers first, plus how many rose/fell and an industry summary."""
    rows = []
    for m in members:
        close, prev = prices.get(m["symbol"], (None, None))
        change = round(close - prev, 2) if close and prev else None
        rows.append({**m, "close": close, "change": change, "pct": round(change / prev * 100, 2) if change is not None else None})
    priced = sorted((r for r in rows if r["pct"] is not None), key=lambda r: r["pct"], reverse=True)
    industries: dict[str, list] = {}
    for r in priced:
        industries.setdefault(r["industry"] or "Other", []).append(r["pct"])
    return {
        "rows": priced + [r for r in rows if r["pct"] is None],
        "advances": sum(r["pct"] > 0 for r in priced),
        "declines": sum(r["pct"] < 0 for r in priced),
        "unchanged": sum(r["pct"] == 0 for r in priced),
        "industries": sorted(
            ({"industry": k, "count": len(v), "avgPct": round(sum(v) / len(v), 2)} for k, v in industries.items()),
            key=lambda i: (-i["count"], i["industry"]),
        ),
    }


async def _nse_index_overview(nse_name: str) -> Optional[dict]:
    """One index's row from NSE allIndices (level, breadth, P/E, P/B, yield, period returns), cached 60 s."""
    if time.time() - _all_indices_cache["at"] > 60:
        try:
            data = await nse_session.get_data("https://www.nseindia.com/api/allIndices")
            _all_indices_cache.update(at=time.time(), rows=data.get("data") or [])
        except Exception as exc:  # keep serving the last copy
            logger.warning("allIndices fetch failed: %s", exc)
    row = next((r for r in _all_indices_cache["rows"] if (r.get("index") or "").upper() == nse_name.upper()), None)
    if not row:
        return None
    out = {k: _number(row.get(k)) for k in _OVERVIEW_FIELDS}
    out["name"] = row.get("index")
    return out


async def _index_members(csv_file: str) -> list[dict]:
    """Constituents from NSE's archive CSV (company, industry, symbol), cached a day."""
    cached = _members_cache.get(csv_file)
    if cached and time.time() - cached[0] < 86400:
        return cached[1]
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        resp = await client.get(f"https://nsearchives.nseindia.com/content/indices/ind_{csv_file}list.csv")
        resp.raise_for_status()
    members = [
        {"symbol": r["Symbol"].strip(), "name": r["Company Name"].strip(), "industry": r["Industry"].strip()}
        for r in csv.DictReader(io.StringIO(resp.text)) if r.get("Symbol")
    ]
    _members_cache[csv_file] = (time.time(), members)
    return members


async def _latest_bhav_prices() -> tuple[Optional[str], dict]:
    """{symbol: (close, previous close)} from the newest NSE bhavcopy, re-checked hourly."""
    if time.time() - _bhav_cache["at"] > 3600 or not _bhav_cache["prices"]:
        for back in range(7):
            day = date.today() - timedelta(days=back)
            df = await asyncio.to_thread(download_bhavcopy, day)
            if df is not None and "PrvsClsgPric" in df.columns:
                prices = {s: (round(float(c), 2), round(float(p), 2)) for s, c, p in zip(df["TckrSymb"], df["ClsPric"], df["PrvsClsgPric"])}
                _bhav_cache.update(at=time.time(), date=day.isoformat(), prices=prices)
                break
    return _bhav_cache["date"], _bhav_cache["prices"]


# Live constituent moves. shortcut: only indices with up to this many members go live, since each new
# member costs one feed subscription and one previous-close lookup; raise it once the daily store holds them.
LIVE_MEMBERS_MAX = 100
LIVE_CACHE_SECONDS = 10
_live_cache: dict[str, tuple[float, dict]] = {}
_live_locks: dict[str, asyncio.Lock] = {}
_fed_indices: set[str] = set()  # indices whose members this process has asked into the feed


def live_prices(members: list[dict], quotes: dict[str, tuple[float, int]], bhav: dict, today: str) -> dict:
    """{symbol: (live price, previous close)} for members with a feed price from today's session.
    The previous close is the latest bhavcopy's close (today's isn't published until the evening)."""
    out = {}
    for m in members:
        quote, close = quotes.get(m["symbol"]), bhav.get(m["symbol"], (None, None))[0]
        if quote and close and datetime.fromtimestamp(quote[1], IST).date().isoformat() == today:
            out[m["symbol"]] = (quote[0], close)
    return out


async def _live_constituents(csv_file: str) -> dict:
    from market import service as market_service  # the feed's request queue

    members = await _index_members(csv_file)
    bhav_date, bhav = await _latest_bhav_prices()
    today = datetime.now(IST).date().isoformat()
    redis = get_redis_client()
    if len(members) > LIVE_MEMBERS_MAX or redis is None or bhav_date == today:  # today's close is out: that's final
        return {"live": False}
    instruments = await get_instruments()
    sids = {m["symbol"]: e["nse"]["sid"] for m in members if (e := instruments.get(m["symbol"])) and e["nse"]}
    if csv_file not in _fed_indices:
        for sid in sids.values():
            await market_service.request_feed(redis, {"exchangeSegment": "NSE_EQ", "securityId": sid})
        _fed_indices.add(csv_file)
    async with redis.pipeline(transaction=False) as pipe:
        for sid in sids.values():
            pipe.hmget(rkey(f"quote:NSE_EQ:{sid}"), "price", "ts")
        raw = await pipe.execute()
    quotes = {sym: (float(p), int(float(ts))) for sym, (p, ts) in zip(sids, raw) if p and ts}
    prices = live_prices(members, quotes, bhav, today)
    if not prices:
        return {"live": False}
    latest = max(quotes[s][1] for s in prices)
    return {"live": True, "asOf": datetime.fromtimestamp(latest, IST).isoformat(), **constituent_moves(members, prices)}


@router.get("/index/{key}/live")
async def index_live(key: str, current_user: User = Depends(get_current_user)):
    """Constituent moves during the session from the live feed: movers, breadth, industries and rows.
    Worked out at most once every 10 seconds per index and shared by every viewer; live=false
    outside the session or for indices too large to stream."""
    key = key.strip().upper()
    index = (await get_indices()).get(key)
    csv_file = INDEX_CONSTITUENTS.get(index["symbol"], (None, None))[1] if index else None
    if not csv_file:
        raise HTTPException(status_code=404, detail="No constituent list for this index")
    cached = _live_cache.get(key)
    if cached and time.time() - cached[0] < LIVE_CACHE_SECONDS:
        return cached[1]
    async with _live_locks.setdefault(key, asyncio.Lock()):
        cached = _live_cache.get(key)
        if cached and time.time() - cached[0] < LIVE_CACHE_SECONDS:
            return cached[1]
        try:
            result = await _live_constituents(csv_file)
        except Exception as exc:  # the page keeps its end-of-day view
            logger.warning("live constituents for %s failed: %s", key, exc)
            result = {"live": False}
        _live_cache[key] = (time.time(), result)
        return result


@router.get("/index/{key}")
async def index_analysis(key: str, current_user: User = Depends(get_current_user)):
    """Everything the index page shows beyond the chart: NSE's overview and constituent moves."""
    index = (await get_indices()).get(key.strip().upper())
    if not index:
        raise HTTPException(status_code=404, detail="Unknown index")
    nse_name, csv_file = INDEX_CONSTITUENTS.get(index["symbol"], (index["name"], None))
    overview = await _nse_index_overview(nse_name) if index["exchange"] == "NSE" else None
    constituents = None
    if csv_file:
        try:
            members = await _index_members(csv_file)
            as_of, prices = await _latest_bhav_prices()
            constituents = {"asOf": as_of, **constituent_moves(members, prices)}
        except Exception as exc:
            logger.warning("constituents for %s failed: %s", key, exc)
    return {"key": key.strip().upper(), "symbol": index["symbol"], "name": index["name"], "exchange": index["exchange"],
            "overview": overview, "constituents": constituents}
