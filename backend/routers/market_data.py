"""
Market Data Router - Live SENSEX & NIFTY data proxy
"""

from fastapi import APIRouter
import httpx
from datetime import datetime, timezone, timedelta

router = APIRouter()

# IST offset: UTC+5:30
IST_OFFSET = timedelta(hours=5, minutes=30)


def get_ist_now():
    """Get current time in IST without pytz dependency"""
    return datetime.now(timezone.utc) + IST_OFFSET


def get_market_status():
    """Determine Indian market status based on current IST time"""
    now = get_ist_now()
    weekday = now.weekday()  # 0=Monday, 6=Sunday

    # Weekend
    if weekday >= 5:
        return "Closed"

    hour = now.hour
    minute = now.minute
    time_val = hour * 60 + minute

    pre_open = 9 * 60       # 9:00 AM
    market_open = 9 * 60 + 15   # 9:15 AM
    market_close = 15 * 60 + 30  # 3:30 PM

    if time_val < pre_open:
        return "Pre-Market"
    elif time_val < market_open:
        return "Pre-Open"
    elif time_val <= market_close:
        return "Open"
    else:
        return "Closed"


# Headers to mimic browser requests
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


@router.get("/live")
async def get_live_market_data():
    """Get live SENSEX and NIFTY data"""
    market_status = get_market_status()
    sensex_data = None
    nifty_data = None

    async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
        # ── SENSEX from BSE ──
        try:
            bse_headers = {
                **BROWSER_HEADERS,
                "Referer": "https://www.bseindia.com/",
                "Origin": "https://www.bseindia.com",
            }
            resp = await client.get(
                "https://api.bseindia.com/RealTimeBseIndiaAPI/api/GetSensexData/w",
                headers=bse_headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                # BSE can return a single object or a list
                item = data[0] if isinstance(data, list) and len(data) > 0 else data if isinstance(data, dict) else None
                if item:
                    # Try multiple field name variations
                    value = item.get("ltp") or item.get("CurrValue") or item.get("last") or "0"
                    change = item.get("Chg") or item.get("change") or "0"
                    pct = item.get("PerChg") or item.get("ChgPer") or item.get("percChange") or "0"
                    
                    # If pct is 0 but we have value and prev_close, calculate it
                    prev_close = item.get("PrvClose") or item.get("prevClose") or item.get("previousClose") or "0"
                    try:
                        val_f = float(str(value).replace(",", ""))
                        prev_f = float(str(prev_close).replace(",", ""))
                        chg_f = float(str(change).replace(",", ""))
                        pct_f = float(str(pct).replace(",", ""))
                        
                        if pct_f == 0 and prev_f > 0:
                            pct_f = round(((val_f - prev_f) / prev_f) * 100, 2)
                            pct = str(pct_f)
                        if chg_f == 0 and prev_f > 0:
                            chg_f = round(val_f - prev_f, 2)
                            change = str(chg_f)
                    except (ValueError, ZeroDivisionError):
                        pass

                    sensex_data = {
                        "name": item.get("IndxNm") or item.get("indexName") or "SENSEX",
                        "value": str(value),
                        "change": str(change),
                        "pct_change": str(pct),
                        "high": str(item.get("High") or item.get("high") or "0"),
                        "low": str(item.get("Low") or item.get("low") or "0"),
                        "open": str(item.get("Open") or item.get("open") or "0"),
                        "prev_close": str(prev_close),
                    }
                    print(f"BSE raw item keys: {list(item.keys())}")
                    print(f"BSE parsed: value={value}, change={change}, pct={pct}")
        except Exception as e:
            print(f"BSE API error: {e}")

        # ── NIFTY from NSE ──
        try:
            nse_headers = {
                **BROWSER_HEADERS,
                "Referer": "https://www.nseindia.com/",
                "Origin": "https://www.nseindia.com",
            }
            
            # Try the user-provided API URL first
            resp = await client.get(
                "https://www.nseindia.com/api/NextApi/apiClient?functionName=getIndexData&&type=All",
                headers=nse_headers,
            )

            if resp.status_code == 200:
                data = resp.json()
                indices = data.get("data", data) if isinstance(data, dict) else data
                if isinstance(indices, list):
                    for idx in indices:
                        name = idx.get("indexName") or idx.get("index") or ""
                        if name == "NIFTY 50":
                            last_val = idx.get("last") or idx.get("closePrice") or 0
                            change_val = round(float(last_val) - float(idx.get("previousClose", 0)), 2)
                            nifty_data = {
                                "name": "NIFTY 50",
                                "value": str(last_val),
                                "change": str(change_val),
                                "pct_change": str(idx.get("percChange", 0)),
                                "high": str(idx.get("high", 0)),
                                "low": str(idx.get("low", 0)),
                                "open": str(idx.get("open", 0)),
                                "prev_close": str(idx.get("previousClose", 0)),
                            }
                            break
            
            # Fallback: try allIndices endpoint
            if nifty_data is None:
                await client.get("https://www.nseindia.com/", headers=nse_headers)
                resp = await client.get(
                    "https://www.nseindia.com/api/allIndices",
                    headers=nse_headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    indices = data.get("data", [])
                    for idx in indices:
                        name = idx.get("index") or idx.get("indexSymbol") or ""
                        if "NIFTY 50" == name:
                            last_val = idx.get("last") or idx.get("closePrice") or 0
                            change_val = round(float(last_val) - float(idx.get("previousClose", 0)), 2)
                            nifty_data = {
                                "name": "NIFTY 50",
                                "value": str(last_val),
                                "change": str(change_val),
                                "pct_change": str(idx.get("percentChange") or idx.get("percChange") or 0),
                                "high": str(idx.get("high", 0)),
                                "low": str(idx.get("low", 0)),
                                "open": str(idx.get("open", 0)),
                                "prev_close": str(idx.get("previousClose", 0)),
                            }
                            break
        except Exception as e:
            print(f"NSE API error: {e}")

    now_ist = get_ist_now()
    return {
        "market_status": market_status,
        "sensex": sensex_data,
        "nifty": nifty_data,
        "timestamp": now_ist.isoformat(),
        "server_time_ist": now_ist.strftime("%H:%M:%S"),
    }
