"""
F&O Analysis Router - Futures and Options data analysis
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
FO_BASE_URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{date}_F_0000.csv.zip"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/zip",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}



# Cache for F&O data to avoid repeated downloads
_fo_cache = {
    "data": {},  # Map date -> DataFrame
    "timestamp": {} # Map date -> timestamp
}
CACHE_DURATION = timedelta(minutes=30)

def download_fo_bhavcopy(target_date: date) -> Optional[pd.DataFrame]:
    """
    Downloads the NSE F&O BhavCopy for a specific date and returns as DataFrame.
    Includes caching and a 5-day look-back if the specific date has no data (unless a specific date was requested explicitly by the user, handling of that is in the caller).
    Actually, to keep it simple and consistent with stocks.py:
    If we want a SPECIFIC date, we try only that.
    If we want 'latest', we try a range.
    
    However, the helper here takes 'target_date'. 
    Let's stick to the simple download logic here, but add caching.
    The caller will handle the "look back" if needed (or we can add a 'search_latest' flag).
    """
    # Check cache first
    date_str = target_date.strftime("%Y-%m-%d")
    now = datetime.now()
    
    if (date_str in _fo_cache["data"] and 
        date_str in _fo_cache["timestamp"] and
        now - _fo_cache["timestamp"][date_str] < CACHE_DURATION):
        return _fo_cache["data"][date_str]

    # Download logic
    url_date_str = target_date.strftime("%Y%m%d")
    url = FO_BASE_URL.format(date=url_date_str)
    
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
            # Find the CSV file - sometimes naming might vary
            csv_filename = next((name for name in z.namelist() if name.endswith('.csv')), None)
            if not csv_filename:
                return None
                
            with z.open(csv_filename) as f:
                df = pd.read_csv(f)
        
        # --- PRE-PROCESSING & CLEANING (Matches Streamlit logic) ---
        # Ensure FinInstrmTp is treated as string, stripped of whitespace, and converted to uppercase
        if 'FinInstrmTp' in df.columns:
            df['FinInstrmTp'] = df['FinInstrmTp'].astype(str).str.strip().str.upper()
        
        if 'TckrSymb' in df.columns:
            df['TckrSymb'] = df['TckrSymb'].astype(str).str.strip()

        # Update cache
        _fo_cache["data"][date_str] = df
        _fo_cache["timestamp"][date_str] = now
        
        return df
        
    except Exception as e:
        print(f"Error downloading F&O BhavCopy for {target_date}: {e}")
        return None


def get_latest_available_data(start_date: date = None) -> tuple[Optional[pd.DataFrame], date]:
    """Try to find the latest available data looking back 5 days."""
    if start_date is None:
        start_date = date.today()
        
    for days_back in range(5):
        target_date = start_date - timedelta(days=days_back)
        df = download_fo_bhavcopy(target_date)
        if df is not None:
            return df, target_date
            
    return None, start_date


@router.get("/data/{target_date}")
async def get_fo_data(
    target_date: str,
    instrument_type: Optional[str] = Query(None, description="Filter by instrument type: FUTSTK, FUTIDX, OPTSTK, OPTIDX"),
    current_user: User = Depends(get_current_user)
):
    """
    Get F&O BhavCopy data for a specific date.
    """
    try:
        parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    df = download_fo_bhavcopy(parsed_date)
    
    if df is None:
        raise HTTPException(status_code=404, detail=f"No F&O data available for {target_date}")
    
    # Filter by instrument type if provided
    if instrument_type and 'FinInstrmTp' in df.columns:
        df = df[df['FinInstrmTp'] == instrument_type.upper()]
    
    return {
        "date": target_date,
        "count": len(df),
        "data": df.fillna("").to_dict(orient='records') # Handle NaNs for JSON serialization
    }


@router.get("/futures/{symbol}")
async def get_futures_data(
    symbol: str,
    target_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get futures data for a specific symbol.
    """
    if target_date:
        try:
            parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            df = download_fo_bhavcopy(parsed_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        # Auto-detect latest date
        df, parsed_date = get_latest_available_data()
    
    if df is None:
        raise HTTPException(status_code=404, detail=f"No F&O data available. Market may be closed.")
    
    # Filter for futures of the given symbol
    futures_df = pd.DataFrame()
    
    if 'FinInstrmTp' in df.columns:
        # First filter by instrument type (FUTSTK, FUTIDX)
        # Note: Streamlit uses 'STF' and 'IDF' which might be different codes in different file versions,
        # but standard NSE Bhavcopy usually uses FUTSTK/FUTIDX. 
        # We'll check for both sets to be safe or rely on the cleaned column.
        
        # Standard format check
        temp_df = df[df['FinInstrmTp'].isin(['FUTSTK', 'FUTIDX', 'STF', 'IDF'])]
        
        # Filter by symbol
        if 'TckrSymb' in temp_df.columns:
            futures_df = temp_df[temp_df['TckrSymb'].str.upper() == symbol.upper()]
        elif 'UndrlygVal' in temp_df.columns:
             futures_df = temp_df[temp_df['UndrlygVal'].str.upper() == symbol.upper()]

    return {
        "symbol": symbol.upper(),
        "date": str(parsed_date),
        "count": len(futures_df),
        "data": futures_df.fillna("").to_dict(orient='records')
    }


@router.get("/options/{symbol}")
async def get_options_data(
    symbol: str,
    target_date: Optional[str] = None,
    option_type: Optional[str] = Query(None, description="CE for Call, PE for Put"),
    current_user: User = Depends(get_current_user)
):
    """
    Get options data for a specific symbol.
    """
    if target_date:
        try:
            parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            df = download_fo_bhavcopy(parsed_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        # Auto-detect latest date
        df, parsed_date = get_latest_available_data()
    
    if df is None:
        raise HTTPException(status_code=404, detail=f"No F&O data available.")
    
    # Filter for options
    options_df = pd.DataFrame()
    
    if 'FinInstrmTp' in df.columns:
        # Filter by instrument type
        temp_df = df[df['FinInstrmTp'].isin(['OPTSTK', 'OPTIDX'])]
        
        # Filter by symbol
        if 'TckrSymb' in temp_df.columns:
            options_df = temp_df[temp_df['TckrSymb'].str.upper() == symbol.upper()]
        
        # Further filter by option type (CE/PE)
        if option_type and not options_df.empty:
            # Check different column possibilities for Option Type
            if 'OptnTp' in options_df.columns:
                options_df = options_df[options_df['OptnTp'] == option_type.upper()]
            elif 'FinInstrmNm' in options_df.columns:
                 options_df = options_df[options_df['FinInstrmNm'].str.contains(option_type.upper(), na=False)]
    
    return {
        "symbol": symbol.upper(),
        "date": str(parsed_date),
        "option_type": option_type,
        "count": len(options_df),
        "data": options_df.head(200).fillna("").to_dict(orient='records') # Limit for performance
    }


@router.get("/nifty")
async def get_nifty_data(
    target_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get NIFTY index futures and options data.
    """
    # Determine the date to fetch
    if target_date:
        try:
            parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            df = download_fo_bhavcopy(parsed_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        # Loop back to find latest data
        df, parsed_date = get_latest_available_data()
    
    if df is None:
        raise HTTPException(status_code=404, detail=f"No F&O data available for {target_date or 'recent dates'}")
    
    # --- Robust Filtering for NIFTY (Matching Streamlit Logic) ---
    nifty_df = pd.DataFrame()
    
    # Strategy 1: Filter by TckrSymb containing 'NIFTY'
    if 'TckrSymb' in df.columns:
         nifty_df = df[df['TckrSymb'].str.contains('NIFTY', case=False, na=False)]
    
    # Strategy 2: If Strategy 1 yields little/nothing, try FinInstrmNm
    if (nifty_df.empty or len(nifty_df) < 10) and 'FinInstrmNm' in df.columns:
        nifty_df2 = df[df['FinInstrmNm'].str.contains('NIFTY', case=False, na=False)]
        nifty_df = pd.concat([nifty_df, nifty_df2]).drop_duplicates()

    if nifty_df.empty:
        # Debug info if still empty
        print(f"DEBUG: No NIFTY data found. Cols: {df.columns.tolist()}")
        raise HTTPException(status_code=404, detail="No NIFTY data found in the file")
    
    # Separate futures and options using robust instrument type check
    # Streamlit logic implies standard types, but let's be broad
    futures_types = ['FUTIDX', 'IDF']
    options_types = ['OPTIDX'] 
    
    futures = nifty_df[nifty_df['FinInstrmTp'].isin(futures_types)]
    options = nifty_df[nifty_df['FinInstrmTp'].isin(options_types)]
    
    # If standard types failed, try looser check
    if futures.empty:
         futures = nifty_df[nifty_df['FinInstrmTp'].astype(str).str.contains('FUT', case=False)]
    if options.empty:
         options = nifty_df[nifty_df['FinInstrmTp'].astype(str).str.contains('OPT', case=False)]

    return {
        "date": str(parsed_date),
        "futures_count": len(futures),
        "options_count": len(options),
        "futures": futures.fillna("").to_dict(orient='records'),
        "options": options.head(200).fillna("").to_dict(orient='records')
    }
