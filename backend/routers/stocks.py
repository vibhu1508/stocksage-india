"""
Stock Comparison Router - BhavCopy download and stock price comparison
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import Optional, List
import pandas as pd
import requests
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
    Filters for EQ/BE series only and validates required columns.
    (Matches logic from stock_comparison_tab.py)
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
            return None  # No data for this date (holiday/weekend)
        
        response.raise_for_status()
        
        # Extract CSV from zip
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            csv_filename = z.namelist()[0]
            with z.open(csv_filename) as f:
                df = pd.read_csv(f)
        
        # --- DATA PROCESSING (Matching stock_comparison_tab.py logic) ---
        
        # Required columns for proper comparison
        required_columns = ['TradDt', 'SctySrs', 'FinInstrmNm', 'ClsPric', 'TckrSymb', 'TtlTradgVol']
        for col in required_columns:
            if col not in df.columns:
                print(f"Missing required column: {col} for {target_date}")
                return None
        
        # Filter to only EQ and BE series (like Streamlit version line 64)
        df = df[df['SctySrs'].isin(['EQ', 'BE'])]
        
        # Convert numeric columns
        df['ClsPric'] = pd.to_numeric(df['ClsPric'], errors='coerce')
        df['TtlTradgVol'] = pd.to_numeric(df['TtlTradgVol'], errors='coerce')
        
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
