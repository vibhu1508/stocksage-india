"""
Stock Comparison Router - BhavCopy download and stock price comparison
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any, Literal
import asyncio
import pandas as pd
import requests
import httpx
import zipfile
import io
import time

from database import get_db
from routers.auth import get_current_user
from models import User

router = APIRouter()

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
    date_str = target_date.strftime("%Y%m%d")
    url = BASE_URL.format(date=date_str)
    
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        # First request to get cookies
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(0.5)
        
        # Download the zip file
        response = session.get(url, timeout=30)
        
        if response.status_code == 404:
            return None
        
        response.raise_for_status()
        
        # Extract CSV from zip
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            csv_filename = z.namelist()[0]
            with z.open(csv_filename) as f:
                # OPTIMIZATION: Only load necessary columns
                target_cols = ['TradDt', 'SctySrs', 'FinInstrmNm', 'ClsPric', 'TckrSymb', 'TtlTradgVol']
                
                # Check headers
                header_check = pd.read_csv(f, nrows=0)
                available_cols = [c for c in target_cols if c in header_check.columns]
                
                f.seek(0)
                df = pd.read_csv(f, usecols=available_cols)
        
        # OPTIMIZATION: Filter early to reduce memory before processing
        if 'SctySrs' in df.columns:
            df = df[df['SctySrs'].isin(['EQ', 'BE'])].copy()
        
        # OPTIMIZATION: Downcast numeric types
        for col in ['ClsPric', 'TtlTradgVol']:
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

# Cache for symbols data to avoid repeated downloads
_symbols_cache = {
    "data": None,
    "timestamp": None
}
CACHE_DURATION = timedelta(hours=1)

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


def get_cached_symbols() -> Optional[pd.DataFrame]:
    """Get symbols data from cache or download if expired/missing."""
    global _symbols_cache
    
    now = datetime.now()
    
    # Check if cache is valid
    if (_symbols_cache["data"] is not None and 
        _symbols_cache["timestamp"] is not None and
        now - _symbols_cache["timestamp"] < CACHE_DURATION):
        return _symbols_cache["data"]
    
    # Try to download fresh data
    today = date.today()
    df = None
    
    for days_back in range(5):
        target_date = today - timedelta(days=days_back)
        df = download_bhavcopy(target_date)
        if df is not None:
            break
    
    if df is not None:
        # Update cache
        _symbols_cache["data"] = df
        _symbols_cache["timestamp"] = now
    
    return df


@router.get("/search")
async def search_symbols(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results to return"),
    current_user: User = Depends(get_current_user)
):
    """
    Search for stock symbols with company names.
    Returns matching symbols with their company names for autocomplete.
    Uses cached data to avoid slow downloads on every request.
    """
    # Get cached symbols data
    df = get_cached_symbols()
    
    if df is None or 'TckrSymb' not in df.columns:
        return {"results": [], "query": q, "count": 0}
    
    # Search for matching symbols
    query_upper = q.upper()
    
    # Get relevant columns
    if 'FinInstrmNm' in df.columns:
        # Has company name
        search_df = df[['TckrSymb', 'FinInstrmNm']].drop_duplicates()
        search_df.columns = ['symbol', 'name']
    else:
        # No company name, just use symbol
        search_df = df[['TckrSymb']].drop_duplicates()
        search_df.columns = ['symbol']
        search_df['name'] = search_df['symbol']
    
    # Filter by query - match on symbol or company name
    mask = (
        search_df['symbol'].str.upper().str.contains(query_upper, na=False) |
        search_df['name'].str.upper().str.contains(query_upper, na=False)
    )
    results = search_df[mask].head(limit)
    
    return {
        "query": q,
        "count": len(results),
        "results": results.to_dict(orient='records')
    }


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
