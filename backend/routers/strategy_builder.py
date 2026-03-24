"""
Strategy Builder Router - Options Strategy Builder Logic and Persistence
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import date, datetime, timedelta, time
import pandas as pd
import requests
import io
import gzip
from typing import List, Optional
from pydantic import BaseModel

from database import get_db
from routers.auth import get_current_user
from models import User, Strategy, Position
from utils.market_utils import get_latest_market_date, IST
import httpx
import asyncio

router = APIRouter()

# --- NSE API Configurations ---
# Updated after 8:00 PM IST on trading days
CONTRACT_URL_TEMPLATE = "https://nsearchives.nseindia.com/content/fo/NSE_FO_contract_{date}.csv.gz"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/x-gzip, application/octet-stream",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

# --- NSE Session Manager ---
class NSESession:
    def __init__(self):
        self.client = httpx.AsyncClient(headers=HEADERS, timeout=15.0, verify=False, follow_redirects=True)
        self.last_init = None

    async def ensure_session(self):
        """Ensures we have fresh cookies from NSE"""
        now = datetime.now()
        if not self.last_init or (now - self.last_init).total_seconds() > 300: # Refresh every 5 mins
            try:
                print("Initializing NSE Session...")
                await self.client.get("https://www.nseindia.com", headers=HEADERS)
                self.last_init = now
            except Exception as e:
                print(f"Session Init Error: {e}")

    async def get_data(self, url: str):
        await self.ensure_session()
        try:
            response = await self.client.get(url, headers=HEADERS)
            if response.status_code == 401: # Potential session expiry
                self.last_init = None
                await self.ensure_session()
                response = await self.client.get(url, headers=HEADERS)
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"API Fetch Error ({url}): {e}")
            raise HTTPException(status_code=502, detail=f"NSE API Error: {str(e)}")

nse_session = NSESession()

# --- Pydantic Schemas ---
class PositionSchema(BaseModel):
    segment: str
    expiry: str
    strike: Optional[float] = None
    option_type: Optional[str] = None
    action: str
    qty: int
    entry_price: float

class StrategySchema(BaseModel):
    name: str
    symbol: str
    positions: List[PositionSchema]

# --- Helper Functions ---

# --- Caching Mechanism ---
_FO_DF_CACHE = None
_SYMBOL_CACHE = []
_CACHE_DATE = None

def get_latest_contract_date() -> date:
    """Gets the latest date for the FO contract file (cutoff 8:00 PM)"""
    now_ist = datetime.now(IST)
    if now_ist.time() < time(20, 0):
        # Use previous market day logic from utils
        return get_latest_market_date(now_ist - timedelta(hours=1)) # Slight offset to ensure cutoff
    return get_latest_market_date(now_ist)

def fetch_fo_contracts() -> pd.DataFrame:
    """Fetches and caches the latest FO contract master CSV"""
    global _FO_DF_CACHE, _CACHE_DATE, _SYMBOL_CACHE
    
    target_date = get_latest_contract_date()
    
    # Return cache if valid
    if _FO_DF_CACHE is not None and _CACHE_DATE == target_date:
        return _FO_DF_CACHE
        
    date_str = target_date.strftime("%d%m%Y")
    url = CONTRACT_URL_TEMPLATE.format(date=date_str)
    
    print(f"Fetching FO contracts for {date_str}...")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 404:
            # Fallback to previous day if today's not yet available
            prev_date = target_date - timedelta(days=1)
            response = requests.get(CONTRACT_URL_TEMPLATE.format(date=prev_date.strftime("%d%m%Y")), headers=HEADERS, timeout=10)
        
        response.raise_for_status()
        
        with gzip.open(io.BytesIO(response.content), 'rt') as f:
            df = pd.read_csv(f)
            _FO_DF_CACHE = df
            _CACHE_DATE = target_date
            
            # Map symbols efficiently (User requested: TckrSymb, MinLot)
            symbol_col = 'TckrSymb'
            if symbol_col not in df.columns:
                symbol_col = next((c for c in df.columns if 'Symb' in c), 'Symbol')
            
            # Filter for indices and stocks only
            _SYMBOL_CACHE = sorted(df[symbol_col].unique().astype(str).tolist())
            
            return df
    except Exception as e:
        print(f"Error fetching FO contracts: {e}")
        return _FO_DF_CACHE if _FO_DF_CACHE is not None else pd.DataFrame()

# --- API Endpoints ---

@router.get("/symbols")
async def get_fo_symbols(current_user: User = Depends(get_current_user)):
    """Fetch all unique symbols available in F&O (Cached)"""
    if not _SYMBOL_CACHE or _CACHE_DATE != get_latest_contract_date():
        fetch_fo_contracts()
    
    if not _SYMBOL_CACHE:
        raise HTTPException(status_code=503, detail="Unable to fetch F&O contract data")
        
    return {"symbols": _SYMBOL_CACHE}

@router.get("/dropdowns/{symbol}")
async def get_dropdown_data(symbol: str, current_user: User = Depends(get_current_user)):
    """Fetch expiries and lot size for a symbol from NSE API"""
    symbol_upper = symbol.upper()
    
    indices = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY']
    is_index = symbol_upper in indices
    
    if is_index:
        # Use getSymbolDerivativesFilter for indices
        url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getSymbolDerivativesFilter&isSymbolIndex=I&symbol={symbol_upper}"
    else:
        url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getOptionChainDropdown&symbol={symbol_upper}"
    
    df = fetch_fo_contracts()
    
    # Get lot size from CSV (MinLot)
    lot_size = 1
    if not df.empty:
        symbol_col = 'TckrSymb' if 'TckrSymb' in df.columns else 'Symbol'
        lot_col = 'MinLot' if 'MinLot' in df.columns else 'LotSize'
        row = df[df[symbol_col] == symbol_upper]
        if not row.empty:
            lot_size = int(row.iloc[0][lot_col])

    try:
        data = await nse_session.get_data(url)
        
        if is_index:
            # Index response: { expiryDate: [...], strikePrice: [...], optionType: [...], ... }
            expiries = data.get('expiryDate', [])
            strike_prices = data.get('strikePrice', [])
            # Filter out '0' from strike prices and convert to numbers
            strikes = [float(s) for s in strike_prices if s and s.strip() != '0']
            
            result = {
                'expiryDates': expiries,
                'strikePrices': strikes,
                'lotSize': lot_size
            }
            return result
        else:
            data['lotSize'] = lot_size
            return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NSE API Error: {str(e)}")

@router.get("/symbol-data/{symbol}")
async def get_symbol_live_data(symbol: str, current_user: User = Depends(get_current_user)):
    """Fetch live spot price from getIndexData (indices) or getSymbolData (stocks)"""
    symbol_upper = symbol.upper()
    
    # Indices mapping: symbol -> indexName in getIndexData response
    indices_map = {
        "NIFTY": "NIFTY 50",
        "BANKNIFTY": "NIFTY BANK",
        "FINNIFTY": "NIFTY FINANCIAL SERVICES",
        "MIDCPNIFTY": "NIFTY MIDCAP SELECT"
    }
    
    if symbol_upper in indices_map:
        # Use getIndexData for ALL indices spot prices
        url = "https://www.nseindia.com/api/NextApi/apiClient?functionName=getIndexData&type=All"
        data = await nse_session.get_data(url)
        
        # Search array for matching index
        target_name = indices_map[symbol_upper]
        index_data = None
        for item in data.get('data', []):
            if item.get('indexName') == target_name:
                index_data = item
                break
        
        if index_data:
            return index_data  # { indexName, last, open, high, low, previousClose, percChange, ... }
        else:
            return {"last": 0, "indexName": target_name}
    else:
        url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getSymbolData&marketType=N&series=EQ&symbol={symbol_upper}"
        return await nse_session.get_data(url)

@router.get("/futures-data/{symbol}")
async def get_futures_live_data(
    symbol: str, 
    expiry: Optional[str] = Query(None), 
    identifier: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """Fetch live futures price from getSymbolDerivativesData"""
    symbol_upper = symbol.upper()
    indices = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY']
    is_index = symbol_upper in indices
    
    if is_index:
        # For indices, fetch all derivatives and extract the nearest FUT entry
        url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getSymbolDerivativesData&symbol={symbol_upper}"
        data = await nse_session.get_data(url)
        
        # Filter FUT entries from data array (identifier starts with FUTIDX)
        all_entries = data.get('data', [])
        fut_entries = [e for e in all_entries if str(e.get('identifier', '')).startswith('FUTIDX')]
        
        if fut_entries:
            # Return nearest (first) futures entry
            return {"futuresData": fut_entries, "nearestFuture": fut_entries[0], "timestamp": data.get('timestamp', '')}
        else:
            return {"futuresData": [], "nearestFuture": None, "timestamp": data.get('timestamp', '')}
    else:
        url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getSymbolDerivativesData&symbol={symbol_upper}&identifier={identifier}&instrumentType=FUT&expiryDt={expiry}"
        return await nse_session.get_data(url)

@router.get("/option-chain/{symbol}")
async def get_option_chain_live_data(
    symbol: str, 
    expiry: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """Fetch full option chain from getOptionChainData"""
    url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getOptionChainData&symbol={symbol.upper()}"
    if expiry:
        url += f"&params=expiryDate={expiry}"
    
    return await nse_session.get_data(url)

@router.post("/save")
async def save_strategy(
    strategy_data: StrategySchema, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save a new strategy with its positions"""
    new_strategy = Strategy(
        user_id=current_user.id,
        name=strategy_data.name,
        symbol=strategy_data.symbol.upper(),
        is_active=True
    )
    db.add(new_strategy)
    db.flush() # Get ID
    
    for pos in strategy_data.positions:
        db.add(Position(
            strategy_id=new_strategy.id,
            segment=pos.segment,
            expiry=pos.expiry,
            strike=pos.strike,
            option_type=pos.option_type,
            action=pos.action.upper(),
            qty=pos.qty,
            entry_price=pos.entry_price
        ))
    
    db.commit()
    db.refresh(new_strategy)
    return {"message": "Strategy saved successfully", "id": new_strategy.id}

@router.get("/user-strategies")
async def get_user_strategies(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all strategies for the current user, categorized into Live and History"""
    strategies = db.query(Strategy).filter(Strategy.user_id == current_user.id).order_by(desc(Strategy.created_at)).all()
    
    live = []
    history = []
    today = date.today()
    
    for s in strategies:
        # Categorize by expiry of positions
        # If any position is not yet expired, it's live
        is_live = False
        s_data = {
            "id": s.id,
            "name": s.name,
            "symbol": s.symbol,
            "created_at": s.created_at,
            "positions": []
        }
        
        for p in s.positions:
            s_data["positions"].append({
                "segment": p.segment,
                "expiry": p.expiry,
                "strike": p.strike,
                "option_type": p.option_type,
                "action": p.action,
                "qty": p.qty,
                "entry_price": p.entry_price
            })
            
            try:
                # Expiry format DD-Mon-YYYY
                p_expiry = datetime.strptime(p.expiry, "%d-%b-%Y").date()
                if p_expiry >= today:
                    is_live = True
            except:
                is_live = True # Default to live if date parsing fails
        
        if is_live:
            live.append(s_data)
        else:
            history.append(s_data)
            
    return {"live": live, "history": history}

@router.delete("/{strategy_id}")
async def delete_strategy(strategy_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete a strategy and its positions"""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id, Strategy.user_id == current_user.id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    db.delete(strategy)
    db.commit()
    return {"message": "Strategy deleted"}
