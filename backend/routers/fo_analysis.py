"""
F&O Analysis Router - Futures and Options data analysis

Data source: NSE UDiFF F&O BhavCopy (daily zip archive).

Column reference (UDiFF format):
    FinInstrmTp   IDF (index futures) | STF (stock futures) | IDO (index options) | STO (stock options)
    TckrSymb      Underlying symbol, e.g. NIFTY / RELIANCE
    XpryDt        Expiry date, ISO format (YYYY-MM-DD)
    StrkPric      Strike price (options only)
    OptnTp        CE | PE
    UndrlygPric   Spot price of the underlying
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import date, datetime, timedelta
from typing import Optional, List, Tuple
import numpy as np
import pandas as pd
import requests
import zipfile
import io
import time

from routers.auth import get_current_user
from models import User
from utils.market_utils import get_latest_market_date

router = APIRouter()

# Configuration
FO_BASE_URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{date}_F_0000.csv.zip"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/zip",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# Instrument type codes. The UDiFF bhavcopy uses IDF/STF/IDO/STO; the older
# bhavcopy format used FUTIDX/FUTSTK/OPTIDX/OPTSTK. Accept both.
INDEX_FUTURES_TYPES = ["IDF", "FUTIDX"]
STOCK_FUTURES_TYPES = ["STF", "FUTSTK"]
INDEX_OPTIONS_TYPES = ["IDO", "OPTIDX"]
STOCK_OPTIONS_TYPES = ["STO", "OPTSTK"]
FUTURES_TYPES = INDEX_FUTURES_TYPES + STOCK_FUTURES_TYPES
OPTIONS_TYPES = INDEX_OPTIONS_TYPES + STOCK_OPTIONS_TYPES

# Only these columns are loaded from the CSV - the raw file has 34.
BHAVCOPY_COLUMNS = [
    'TradDt', 'FinInstrmTp', 'TckrSymb', 'XpryDt', 'StrkPric', 'OptnTp',
    'FinInstrmNm', 'ClsPric', 'PrvsClsgPric', 'UndrlygPric', 'SttlmPric',
    'OpnIntrst', 'ChngInOpnIntrst', 'TtlTradgVol', 'TtlTrfVal',
]
NUMERIC_COLUMNS = [
    'StrkPric', 'ClsPric', 'PrvsClsgPric', 'UndrlygPric', 'SttlmPric',
    'OpnIntrst', 'ChngInOpnIntrst', 'TtlTradgVol', 'TtlTrfVal',
]

# Cache for F&O data to avoid repeated downloads.
# Limited to the 2 most recent dates to prevent memory bloat.
_fo_cache = {
    "data": {},       # Map date -> DataFrame
    "timestamp": {}   # Map date -> timestamp
}
CACHE_DURATION = timedelta(minutes=30)
MAX_CACHE_ENTRIES = 2


def download_fo_bhavcopy(target_date: date) -> Optional[pd.DataFrame]:
    """
    Downloads the NSE F&O BhavCopy for a specific date and returns it as a
    DataFrame with the derived momentum columns already computed.
    """
    # Check cache first
    date_str = target_date.strftime("%Y-%m-%d")
    now = datetime.now()

    if (date_str in _fo_cache["data"] and
        date_str in _fo_cache["timestamp"] and
        now - _fo_cache["timestamp"][date_str] < CACHE_DURATION):
        return _fo_cache["data"][date_str]

    url_date_str = target_date.strftime("%Y%m%d")
    url = FO_BASE_URL.format(date=url_date_str)

    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        # First request to get cookies
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(0.5)

        response = session.get(url, timeout=30)

        if response.status_code == 404:
            return None

        response.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            csv_filename = next((name for name in z.namelist() if name.endswith('.csv')), None)
            if not csv_filename:
                return None
            df = _read_bhavcopy_csv(z, csv_filename)

        df = prepare_fo_frame(df)

        # Update cache with size limit enforcement (LRU-ish)
        if len(_fo_cache["data"]) >= MAX_CACHE_ENTRIES:
            oldest_date = sorted(_fo_cache["timestamp"].items(), key=lambda x: x[1])[0][0]
            del _fo_cache["data"][oldest_date]
            del _fo_cache["timestamp"][oldest_date]

        _fo_cache["data"][date_str] = df
        _fo_cache["timestamp"][date_str] = now

        return df

    except Exception as e:
        print(f"Error downloading F&O BhavCopy for {target_date}: {e}")
        return None


def _read_bhavcopy_csv(archive: zipfile.ZipFile, csv_filename: str) -> pd.DataFrame:
    """Read only the columns we need, tolerating format differences."""
    with archive.open(csv_filename) as f:
        header = pd.read_csv(f, nrows=0)

    usecols = [c for c in BHAVCOPY_COLUMNS if c in header.columns]
    with archive.open(csv_filename) as f:
        return pd.read_csv(f, usecols=usecols)


def prepare_fo_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise dtypes and add the derived columns every tab depends on:
    pct_price_change (close vs previous close) and pct_oi_change (change in OI
    against yesterday's OI).
    """
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.replace(',', '', regex=False)
            df[col] = pd.to_numeric(df[col], errors='coerce')

    for col in ('FinInstrmTp', 'OptnTp'):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper().replace({'NAN': None})

    for col in ('TckrSymb', 'XpryDt', 'FinInstrmNm'):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # % price change vs previous close
    if {'ClsPric', 'PrvsClsgPric'}.issubset(df.columns):
        prev_close = df['PrvsClsgPric'].replace(0, np.nan)
        df['pct_price_change'] = ((df['ClsPric'] - prev_close) / prev_close * 100).round(2)
        df['pct_price_change'] = df['pct_price_change'].fillna(0)

    # % OI change against yesterday's open interest
    if {'OpnIntrst', 'ChngInOpnIntrst'}.issubset(df.columns):
        prev_oi = (df['OpnIntrst'] - df['ChngInOpnIntrst']).replace(0, np.nan)
        df['pct_oi_change'] = (df['ChngInOpnIntrst'] / prev_oi * 100).round(2)
        df['pct_oi_change'] = df['pct_oi_change'].replace([np.inf, -np.inf], np.nan).fillna(0)

    return df


def get_latest_available_data(start_date: date = None) -> Tuple[Optional[pd.DataFrame], date]:
    """Try to find the latest available data using the market utils latest date."""
    if start_date is None:
        start_date = get_latest_market_date()

    df = download_fo_bhavcopy(start_date)
    if df is not None:
        return df, start_date

    # Fallback to looking back if the calculated date is not yet published
    for days_back in range(1, 6):
        target_date = start_date - timedelta(days=days_back)
        df = download_fo_bhavcopy(target_date)
        if df is not None:
            return df, target_date

    return None, start_date


def _resolve_frame(target_date: Optional[str]) -> Tuple[pd.DataFrame, date]:
    """Load the bhavcopy for an explicit date, or auto-detect the latest one."""
    if target_date:
        try:
            parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        df = download_fo_bhavcopy(parsed_date)
    else:
        df, parsed_date = get_latest_available_data()

    if df is None:
        raise HTTPException(
            status_code=404,
            detail=f"No F&O data available for {target_date or 'recent dates'}. Market may be closed."
        )
    return df, parsed_date


def _records(df: pd.DataFrame) -> List[dict]:
    """JSON-safe records: NaN/inf become null rather than NaN literals."""
    if df is None or df.empty:
        return []
    clean = df.replace([np.inf, -np.inf], np.nan)
    return clean.astype(object).where(pd.notna(clean), None).to_dict(orient='records')


def _sorted_expiries(df: pd.DataFrame) -> List[str]:
    """Unique expiry dates, chronologically sorted."""
    if 'XpryDt' not in df.columns or df.empty:
        return []
    expiries = pd.Series(df['XpryDt'].dropna().unique())
    order = pd.to_datetime(expiries, errors='coerce', format='mixed')
    return expiries[order.argsort()].tolist()


def _parse_expiry_series(values: pd.Series) -> pd.Series:
    """Parse XpryDt regardless of ISO (2026-03-26) or legacy (26-Mar-2026) format."""
    parsed = pd.to_datetime(values, errors='coerce', format='mixed')
    if parsed.isna().any():
        fallback = pd.to_datetime(values, errors='coerce', format='%d-%b-%Y')
        parsed = parsed.fillna(fallback)
    return parsed


def _symbol_frame(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Rows for a symbol, matching on ticker first and instrument name as fallback."""
    upper = symbol.strip().upper()
    if 'TckrSymb' in df.columns:
        matched = df[df['TckrSymb'].str.upper() == upper]
        if not matched.empty:
            return matched
    if 'FinInstrmNm' in df.columns:
        return df[df['FinInstrmNm'].str.upper().str.startswith(upper, na=False)]
    return df.iloc[0:0]


def _build_option_chain(
    options_df: pd.DataFrame,
    symbol: str,
    expiry: Optional[str],
) -> dict:
    """
    Merge CE and PE legs on strike price into a single option-chain table,
    with per-strike PCR and a summary block (total OI, PCR, support/resistance).
    """
    symbol_df = _symbol_frame(options_df, symbol)
    available_expiries = _sorted_expiries(symbol_df)

    selected_expiry = expiry if expiry and expiry in available_expiries else (
        available_expiries[0] if available_expiries else None
    )

    empty = {
        "symbol": symbol.upper(),
        "expiry": selected_expiry,
        "available_expiries": available_expiries,
        "underlying_price": None,
        "chain": [],
        "summary": None,
    }

    if selected_expiry is None:
        return empty

    rows = symbol_df[symbol_df['XpryDt'] == selected_expiry]
    if rows.empty or 'OptnTp' not in rows.columns:
        return empty

    leg_cols = ['StrkPric', 'ClsPric', 'OpnIntrst', 'ChngInOpnIntrst', 'pct_oi_change', 'TtlTradgVol']
    leg_cols = [c for c in leg_cols if c in rows.columns]

    def leg(option_type: str, prefix: str) -> pd.DataFrame:
        side = rows[rows['OptnTp'] == option_type][leg_cols]
        return side.rename(columns={c: f"{prefix}_{c}" for c in leg_cols if c != 'StrkPric'})

    ce = leg('CE', 'CE')
    pe = leg('PE', 'PE')

    if ce.empty and pe.empty:
        return empty

    chain = pd.merge(ce, pe, on='StrkPric', how='outer').sort_values('StrkPric')

    # Per-strike Put-Call OI ratio
    if {'PE_OpnIntrst', 'CE_OpnIntrst'}.issubset(chain.columns):
        chain['PCR'] = (chain['PE_OpnIntrst'] / chain['CE_OpnIntrst'].replace(0, np.nan)).round(2)

    underlying = None
    if 'UndrlygPric' in rows.columns:
        spot = rows['UndrlygPric'].dropna()
        if not spot.empty:
            underlying = round(float(spot.median()), 2)

    total_ce_oi = float(chain['CE_OpnIntrst'].sum()) if 'CE_OpnIntrst' in chain.columns else 0.0
    total_pe_oi = float(chain['PE_OpnIntrst'].sum()) if 'PE_OpnIntrst' in chain.columns else 0.0

    def peak_strike(column: str) -> Optional[float]:
        if column not in chain.columns or chain[column].dropna().empty:
            return None
        return float(chain.loc[chain[column].idxmax(), 'StrkPric'])

    atm_strike = None
    if underlying is not None and not chain['StrkPric'].dropna().empty:
        atm_strike = float(chain.loc[(chain['StrkPric'] - underlying).abs().idxmin(), 'StrkPric'])

    summary = {
        "total_ce_oi": total_ce_oi,
        "total_pe_oi": total_pe_oi,
        "pcr": round(total_pe_oi / total_ce_oi, 2) if total_ce_oi else None,
        "total_ce_oi_change": float(chain['CE_ChngInOpnIntrst'].sum()) if 'CE_ChngInOpnIntrst' in chain.columns else 0.0,
        "total_pe_oi_change": float(chain['PE_ChngInOpnIntrst'].sum()) if 'PE_ChngInOpnIntrst' in chain.columns else 0.0,
        "max_ce_oi_strike": peak_strike('CE_OpnIntrst'),   # strongest resistance
        "max_pe_oi_strike": peak_strike('PE_OpnIntrst'),   # strongest support
        "atm_strike": atm_strike,
        "strike_count": int(len(chain)),
    }

    return {
        "symbol": symbol.upper(),
        "expiry": selected_expiry,
        "available_expiries": available_expiries,
        "underlying_price": underlying,
        "chain": _records(chain),
        "summary": summary,
    }


@router.get("/data/{target_date}")
async def get_fo_data(
    target_date: str,
    instrument_type: Optional[str] = Query(None, description="Filter by instrument type: IDF, STF, IDO, STO"),
    current_user: User = Depends(get_current_user)
):
    """Get raw F&O BhavCopy data for a specific date."""
    df, parsed_date = _resolve_frame(target_date)

    if instrument_type and 'FinInstrmTp' in df.columns:
        df = df[df['FinInstrmTp'] == instrument_type.upper()]

    return {
        "date": str(parsed_date),
        "count": len(df),
        "data": _records(df),
    }


@router.get("/futures/{symbol}")
async def get_futures_data(
    symbol: str,
    target_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get all futures contracts for a specific symbol, across expiries."""
    df, parsed_date = _resolve_frame(target_date)

    futures_df = df.iloc[0:0]
    if 'FinInstrmTp' in df.columns:
        futures_df = _symbol_frame(df[df['FinInstrmTp'].isin(FUTURES_TYPES)], symbol)
        if not futures_df.empty:
            futures_df = futures_df.sort_values('XpryDt')

    return {
        "symbol": symbol.upper(),
        "date": str(parsed_date),
        "count": len(futures_df),
        "data": _records(futures_df),
    }


@router.get("/futures-table")
async def get_futures_table(
    target_date: Optional[str] = None,
    segment: str = Query("index", description="'index' for index futures (IDF), 'stock' for stock futures (STF)"),
    expiry: Optional[str] = Query(None, description="Expiry date (YYYY-MM-DD). Omit for all expiries."),
    symbol: Optional[str] = Query(None, description="Ticker symbol. Omit for all symbols."),
    current_user: User = Depends(get_current_user)
):
    """
    Futures tab: index (IDF) or stock (STF) futures with price/OI momentum,
    plus the filter values and the OI-by-expiry series used for the charts.
    """
    df, parsed_date = _resolve_frame(target_date)

    if 'FinInstrmTp' not in df.columns:
        raise HTTPException(status_code=400, detail="Invalid BhavCopy format: missing FinInstrmTp column.")

    types = INDEX_FUTURES_TYPES if segment.lower() == "index" else STOCK_FUTURES_TYPES
    segment_df = df[df['FinInstrmTp'].isin(types)]

    if segment_df.empty:
        return {
            "date": str(parsed_date),
            "segment": segment.lower(),
            "expiry": None,
            "symbol": None,
            "available_expiries": [],
            "available_symbols": [],
            "count": 0,
            "rows": [],
            "oi_by_expiry": [],
        }

    available_expiries = _sorted_expiries(segment_df)

    filtered = segment_df
    selected_expiry = expiry if expiry and expiry in available_expiries else None
    if selected_expiry:
        filtered = filtered[filtered['XpryDt'] == selected_expiry]

    available_symbols = sorted(filtered['TckrSymb'].dropna().unique().tolist())

    selected_symbol = None
    if symbol and symbol.upper() != 'ALL':
        selected_symbol = symbol.upper()
        filtered = filtered[filtered['TckrSymb'].str.upper() == selected_symbol]

    display_cols = [
        'TckrSymb', 'FinInstrmNm', 'XpryDt', 'UndrlygPric', 'ClsPric',
        'PrvsClsgPric', 'pct_price_change', 'OpnIntrst', 'ChngInOpnIntrst', 'pct_oi_change',
    ]
    display_cols = [c for c in display_cols if c in filtered.columns]
    rows = filtered[display_cols].sort_values(['TckrSymb', 'XpryDt']) if not filtered.empty else filtered

    # Aggregated OI per expiry per symbol, for the bar charts
    oi_by_expiry = []
    if not filtered.empty and {'XpryDt', 'TckrSymb', 'OpnIntrst'}.issubset(filtered.columns):
        grouped = (
            filtered.groupby(['XpryDt', 'TckrSymb'], as_index=False)[['OpnIntrst', 'ChngInOpnIntrst']]
            .sum()
            .sort_values('XpryDt')
        )
        oi_by_expiry = _records(grouped)

    return {
        "date": str(parsed_date),
        "segment": segment.lower(),
        "expiry": selected_expiry,
        "symbol": selected_symbol,
        "available_expiries": available_expiries,
        "available_symbols": available_symbols,
        "count": len(rows),
        "rows": _records(rows),
        "oi_by_expiry": oi_by_expiry,
    }


@router.get("/options/{symbol}")
async def get_options_data(
    symbol: str,
    target_date: Optional[str] = None,
    expiry: Optional[str] = Query(None, description="Expiry date (YYYY-MM-DD). Defaults to nearest."),
    option_type: Optional[str] = Query(None, description="CE for Call, PE for Put"),
    current_user: User = Depends(get_current_user)
):
    """
    Options tab: the CE/PE option chain for a symbol and expiry, with per-strike
    PCR and an OI summary. Also returns the flat rows for backwards compatibility.
    """
    df, parsed_date = _resolve_frame(target_date)

    if 'FinInstrmTp' not in df.columns:
        raise HTTPException(status_code=400, detail="Invalid BhavCopy format: missing FinInstrmTp column.")

    all_options = df[df['FinInstrmTp'].isin(OPTIONS_TYPES)]
    available_symbols = sorted(all_options['TckrSymb'].dropna().unique().tolist())

    chain_payload = _build_option_chain(all_options, symbol, expiry)

    # Flat rows (legacy `data` key), optionally narrowed to CE or PE
    flat = _symbol_frame(all_options, symbol)
    if chain_payload["expiry"]:
        flat = flat[flat['XpryDt'] == chain_payload["expiry"]]
    if option_type and not flat.empty and 'OptnTp' in flat.columns:
        flat = flat[flat['OptnTp'] == option_type.upper()]
    if not flat.empty:
        flat = flat.sort_values(['StrkPric', 'OptnTp'])

    return {
        "date": str(parsed_date),
        "option_type": option_type,
        "available_symbols": available_symbols,
        "count": len(flat),
        "data": _records(flat),
        **chain_payload,
    }


@router.get("/nifty")
async def get_nifty_data(
    target_date: Optional[str] = None,
    symbol: str = Query("NIFTY", description="Index symbol: NIFTY, BANKNIFTY, FINNIFTY, ..."),
    expiry: Optional[str] = Query(None, description="Expiry date (YYYY-MM-DD). Defaults to nearest."),
    current_user: User = Depends(get_current_user)
):
    """
    NIFTY Index tab: index option chain plus the index futures contracts for
    the same underlying.
    """
    df, parsed_date = _resolve_frame(target_date)

    if 'FinInstrmTp' not in df.columns:
        raise HTTPException(status_code=400, detail="Invalid BhavCopy format: missing FinInstrmTp column.")

    index_options = df[df['FinInstrmTp'].isin(INDEX_OPTIONS_TYPES)]
    index_futures = df[df['FinInstrmTp'].isin(INDEX_FUTURES_TYPES)]

    if index_options.empty and index_futures.empty:
        raise HTTPException(status_code=404, detail="No index derivatives found in this BhavCopy.")

    available_symbols = sorted(
        set(index_options['TckrSymb'].dropna().unique()) | set(index_futures['TckrSymb'].dropna().unique())
    )

    selected_symbol = symbol.strip().upper()
    if selected_symbol not in available_symbols:
        selected_symbol = 'NIFTY' if 'NIFTY' in available_symbols else (available_symbols[0] if available_symbols else selected_symbol)

    chain_payload = _build_option_chain(index_options, selected_symbol, expiry)

    futures = _symbol_frame(index_futures, selected_symbol)
    if not futures.empty:
        futures = futures.sort_values('XpryDt')

    options_rows = _symbol_frame(index_options, selected_symbol)
    if chain_payload["expiry"]:
        options_rows = options_rows[options_rows['XpryDt'] == chain_payload["expiry"]]
    if not options_rows.empty:
        options_rows = options_rows.sort_values(['StrkPric', 'OptnTp'])

    return {
        "date": str(parsed_date),
        "available_symbols": available_symbols,
        "futures_count": len(futures),
        "options_count": len(options_rows),
        "futures": _records(futures),
        "options": _records(options_rows),
        **chain_payload,
    }


@router.get("/futures-analysis")
async def get_futures_analysis(
    target_date: Optional[str] = None,
    expiry_month: Optional[str] = Query(None, description="Expiry as 'YYYY-MM-DD' or 'MAR-2026'"),
    current_user: User = Depends(get_current_user)
):
    """
    Momentum screener: long buildup, short buildup, short covering and long
    unwinding for futures contracts of the selected expiry.
    """
    df, parsed_date = _resolve_frame(target_date)

    if 'FinInstrmTp' not in df.columns:
        raise HTTPException(status_code=400, detail="Invalid BhavCopy format: Missing FinInstrmTp column.")

    df_fut = df[df['FinInstrmTp'].isin(FUTURES_TYPES)].copy()

    if df_fut.empty:
        raise HTTPException(status_code=404, detail="No Futures data found in this BhavCopy.")

    df_fut['ActualExpiry'] = _parse_expiry_series(df_fut['XpryDt'])

    # Expiry dropdown values, chronologically ordered
    available_expiries_list = (
        df_fut[['XpryDt', 'ActualExpiry']]
        .dropna()
        .drop_duplicates('XpryDt')
        .sort_values('ActualExpiry')['XpryDt']
        .tolist()
    )

    if expiry_month:
        token = expiry_month.strip()
        month_labels = df_fut['ActualExpiry'].dt.strftime('%b-%Y').str.upper()
        selected = df_fut[(df_fut['XpryDt'] == token) | (month_labels == token.upper())]
        if selected.empty:
            # Last resort: substring match, so '2026-03' or 'MAR' still narrows down
            selected = df_fut[df_fut['XpryDt'].str.contains(token, case=False, na=False)]
        df_fut = selected
    else:
        current_expiry = df_fut['ActualExpiry'].min()
        df_fut = df_fut[df_fut['ActualExpiry'] == current_expiry]

    if df_fut.empty:
        raise HTTPException(status_code=404, detail="No data available for the specified expiry contract.")

    result_cols = [
        'TckrSymb', 'XpryDt', 'ClsPric', 'PrvsClsgPric', 'pct_price_change',
        'UndrlygPric', 'OpnIntrst', 'ChngInOpnIntrst', 'pct_oi_change',
    ]
    output_df = df_fut[[c for c in result_cols if c in df_fut.columns]]

    # Buildups: open interest rising
    buildup_df = output_df[output_df['pct_oi_change'] > 0]

    long_buildup = buildup_df[buildup_df['pct_price_change'] > 0].sort_values(
        by=['pct_oi_change', 'pct_price_change'], ascending=[False, False]
    )
    short_buildup = buildup_df[buildup_df['pct_price_change'] < 0].sort_values(
        by=['pct_oi_change', 'pct_price_change'], ascending=[False, True]
    )

    # Unwinding / covering: open interest falling
    unwind_df = output_df[output_df['pct_oi_change'] < 0]

    short_covering = unwind_df[unwind_df['pct_price_change'] > 0].sort_values(
        by=['pct_oi_change', 'pct_price_change'], ascending=[True, False]
    )
    long_unwinding = unwind_df[unwind_df['pct_price_change'] < 0].sort_values(
        by=['pct_oi_change', 'pct_price_change'], ascending=[True, True]
    )

    return {
        "date": str(parsed_date),
        "expiry_date": str(df_fut['XpryDt'].iloc[0]),
        "available_expiries": available_expiries_list,
        "top_10": _records(long_buildup.head(10)),
        "bottom_10": _records(short_buildup.head(10)),
        "short_covering": _records(short_covering.head(10)),
        "long_unwinding": _records(long_unwinding.head(10)),
    }
