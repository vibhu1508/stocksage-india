"""
Market Data Router - Live SENSEX & NIFTY data proxy
"""

from fastapi import APIRouter
import httpx
from datetime import datetime
import pytz

router = APIRouter()

# Indian Standard Time
IST = pytz.timezone("Asia/Kolkata")

# Headers to mimic browser requests
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


def get_market_status():
    """Determine Indian market status based on current IST time"""
    now = datetime.now(IST)
    weekday = now.weekday()  # 0=Monday, 6=Sunday

    # Weekend
    if weekday >= 5:
        return "Closed"

    hour = now.hour
    minute = now.minute
    time_val = hour * 60 + minute

    pre_open = 9 * 60  # 9:00 AM
    market_open = 9 * 60 + 15  # 9:15 AM
    market_close = 15 * 60 + 30  # 3:30 PM

    if time_val < pre_open:
        return "Pre-Market"
    elif time_val < market_open:
        return "Pre-Open"
    elif time_val <= market_close:
        return "Open"
    else:
        return "Closed"


@router.get("/live")
async def get_live_market_data():
    """Get live SENSEX and NIFTY data"""
    market_status = get_market_status()
    sensex_data = None
    nifty_data = None

    async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
        # Fetch SENSEX data from BSE
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
                # BSE returns a list, get the first item (SENSEX)
                if isinstance(data, list) and len(data) > 0:
                    item = data[0]
                    sensex_data = {
                        "name": item.get("IndxNm", "SENSEX"),
                        "value": item.get("ltp", item.get("CurrValue", "0")),
                        "change": item.get("Chg", "0"),
                        "pct_change": item.get("ChgPer", item.get("PerChg", "0")),
                        "high": item.get("High", "0"),
                        "low": item.get("Low", "0"),
                        "open": item.get("Open", "0"),
                        "prev_close": item.get("PrvClose", "0"),
                    }
                elif isinstance(data, dict):
                    sensex_data = {
                        "name": data.get("IndxNm", "SENSEX"),
                        "value": data.get("ltp", data.get("CurrValue", "0")),
                        "change": data.get("Chg", "0"),
                        "pct_change": data.get("ChgPer", data.get("PerChg", "0")),
                        "high": data.get("High", "0"),
                        "low": data.get("Low", "0"),
                        "open": data.get("Open", "0"),
                        "prev_close": data.get("PrvClose", "0"),
                    }
        except Exception as e:
            print(f"BSE API error: {e}")

        # Fetch NIFTY data from NSE
        try:
            # NSE requires a session cookie - first hit the homepage
            nse_headers = {
                **BROWSER_HEADERS,
                "Referer": "https://www.nseindia.com/",
                "Origin": "https://www.nseindia.com",
            }
            # Get session cookies
            await client.get("https://www.nseindia.com/", headers=nse_headers)

            resp = await client.get(
                "https://www.nseindia.com/api/allIndices",
                headers=nse_headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                indices = data.get("data", [])
                for idx in indices:
                    if idx.get("index") == "NIFTY 50" or idx.get("indexSymbol") == "NIFTY 50":
                        nifty_data = {
                            "name": "NIFTY 50",
                            "value": str(idx.get("last", idx.get("closePrice", "0"))),
                            "change": str(idx.get("variation", "0")),
                            "pct_change": str(idx.get("percentChange", "0")),
                            "high": str(idx.get("high", "0")),
                            "low": str(idx.get("low", "0")),
                            "open": str(idx.get("open", "0")),
                            "prev_close": str(idx.get("previousClose", "0")),
                        }
                        break
        except Exception as e:
            print(f"NSE API error: {e}")

    return {
        "market_status": market_status,
        "sensex": sensex_data,
        "nifty": nifty_data,
        "timestamp": datetime.now(IST).isoformat(),
    }
