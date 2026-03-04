from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import requests as req
import time
import json
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/charts", tags=["charts"])

# ─── NSE API Base URLs ──────────────────────────────────────────────────────────

NSE_CHART_BASE = "https://charting.nseindia.com/v1"
NSE_QUOTE_BASE = "https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Cache for resolved tokens  {symbol_key -> {scripcode, symbol, type, description}}
_token_cache: dict = {}


# ─── NSE Helpers ─────────────────────────────────────────────────────────────────

def _resolve_nse_token(symbol: str) -> dict | None:
    """Resolve a stock/index symbol to its NSE charting token via symbolsDynamic."""
    key = symbol.strip().upper()
    if key in _token_cache:
        return _token_cache[key]

    # Try direct query first
    query = key
    try:
        r = req.get(
            f"{NSE_CHART_BASE}/exchanges/symbolsDynamic",
            params={"symbol": query, "segment": ""},
            headers=NSE_HEADERS,
            timeout=10,
        )
        data = r.json()
        if data.get("status") and data.get("data"):
            item = data["data"][0]
            result = {
                "scripcode": item["scripcode"],
                "symbol": item["symbol"],
                "type": item.get("type", "Equity"),
                "description": item.get("description", ""),
            }
            _token_cache[key] = result
            return result
    except Exception:
        pass

    # Try with -EQ suffix for equities
    if not query.endswith("-EQ") and not any(x in query for x in ["NIFTY", "SENSEX", "BANK"]):
        try:
            r = req.get(
                f"{NSE_CHART_BASE}/exchanges/symbolsDynamic",
                params={"symbol": f"{query}-EQ", "segment": ""},
                headers=NSE_HEADERS,
                timeout=10,
            )
            data = r.json()
            if data.get("status") and data.get("data"):
                item = data["data"][0]
                result = {
                    "scripcode": item["scripcode"],
                    "symbol": item["symbol"],
                    "type": item.get("type", "Equity"),
                    "description": item.get("description", ""),
                }
                _token_cache[key] = result
                return result
        except Exception:
            pass

    return None


def _clean_symbol_for_nse(symbol: str) -> str:
    """Strip yfinance-style suffixes and convert index symbols to NSE names."""
    s = symbol.strip().upper()
    if s == "^NSEI":
        return "NIFTY"
    if s == "^NSEBANK":
        return "NIFTY BANK"
    if s == "^BSESN":
        return "SENSEX"
    for suffix in (".NS", ".BO", "-EQ"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return s


def _get_nse_symbol_for_quote(symbol: str) -> str:
    """Get the clean NSE symbol for the quote API (without -EQ suffix)."""
    s = _clean_symbol_for_nse(symbol)
    return s


def _fetch_nse_history(
    scripcode: str,
    nse_symbol: str,
    symbol_type: str,
    chart_type: str = "D",
    time_interval: int = 1,
    from_ts: int = 0,
    to_ts: int | None = None,
) -> list[dict]:
    """
    Fetch OHLCV history from charting.nseindia.com.
    chart_type: D=Daily, W=Weekly, M=Monthly, I=Intraday
    time_interval: 1=1min, 5=5min, 15=15min (only for chart_type=I)
    """
    if to_ts is None:
        to_ts = int(time.time())

    params = {
        "token": scripcode,
        "fromDate": from_ts,
        "toDate": to_ts,
        "symbol": nse_symbol,
        "symbolType": symbol_type,
        "chartType": chart_type,
        "timeInterval": time_interval,
    }
    try:
        r = req.get(
            f"{NSE_CHART_BASE}/charts/symbolHistoricalData",
            params=params,
            headers=NSE_HEADERS,
            timeout=15,
        )
        data = r.json()
        if data.get("status"):
            return data.get("data", [])
    except Exception:
        pass
    return []


def _period_to_from_ts(period: str) -> int:
    """Convert a period string to a fromDate unix timestamp."""
    now = int(time.time())
    mapping = {
        "1d": 1 * 86400,
        "5d": 5 * 86400,
        "1mo": 30 * 86400,
        "3mo": 90 * 86400,
        "6mo": 180 * 86400,
        "1y": 365 * 86400,
        "2y": 2 * 365 * 86400,
        "5y": 5 * 365 * 86400,
        "10y": 10 * 365 * 86400,
        "max": now,
    }
    seconds = mapping.get(period, 365 * 86400)
    if period == "max":
        return 0
    return now - seconds


def _nse_quote_api(function_name: str, params: dict) -> dict | list | None:
    """Call the NSE NextApi GetQuoteApi."""
    try:
        query_params = {"functionName": function_name}
        query_params.update(params)
        r = req.get(NSE_QUOTE_BASE, params=query_params, headers=NSE_HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


# ─── Search ──────────────────────────────────────────────────────────────────────

@router.get("/search")
async def search_tickers(q: str = Query(..., min_length=2)):
    """Search for stock tickers using NSE symbolsDynamic."""
    try:
        r = req.get(
            f"{NSE_CHART_BASE}/exchanges/symbolsDynamic",
            params={"symbol": q.strip().upper(), "segment": ""},
            headers=NSE_HEADERS,
            timeout=10,
        )
        nse_data = r.json()
        quotes = []
        if nse_data.get("status") and nse_data.get("data"):
            for item in nse_data["data"][:15]:
                quotes.append({
                    "symbol": item.get("symbol", ""),
                    "name": item.get("description", ""),
                    "exchange": item.get("exchange", "NSE"),
                    "type": item.get("type", ""),
                })
        return {"results": quotes}
    except Exception as e:
        return {"results": [], "error": str(e)}


# ─── Quote ───────────────────────────────────────────────────────────────────────

@router.get("/quote")
async def get_quote(symbol: str = Query(...)):
    """Get live quote using NSE getSymbolData API."""
    try:
        clean = _clean_symbol_for_nse(symbol)

        # Try NSE quote API first (for equities)
        data = _nse_quote_api("getSymbolData", {
            "marketType": "N",
            "series": "EQ",
            "symbol": clean,
        })

        if data and isinstance(data, dict) and data.get("equityResponse"):
            eq = data["equityResponse"][0]
            meta = eq.get("metaData", {})
            trade = eq.get("tradeInfo", {})
            sec = eq.get("securityInfo", {}) if "securityInfo" in eq else {}

            price = meta.get("closePrice") or meta.get("lastPrice", 0)
            if isinstance(price, str):
                price = float(price.replace(",", "")) if price else 0
            prev_close = meta.get("previousClose", 0)
            if isinstance(prev_close, str):
                prev_close = float(prev_close.replace(",", "")) if prev_close else 0

            change = meta.get("change", 0)
            pct_change = meta.get("pChange", 0)

            return {
                "symbol": symbol,
                "name": meta.get("companyName", clean),
                "price": round(float(price), 2),
                "previousClose": round(float(prev_close), 2),
                "change": round(float(change), 2),
                "pctChange": round(float(pct_change), 2),
                "open": float(meta.get("open", 0)),
                "dayHigh": float(meta.get("dayHigh", 0)),
                "dayLow": float(meta.get("dayLow", 0)),
                "volume": int(trade.get("totalTradedVolume", 0)),
                "marketCap": 0,
                "fiftyTwoWeekHigh": float(sec.get("week52High", 0)) if sec else 0,
                "fiftyTwoWeekLow": float(sec.get("week52Low", 0)) if sec else 0,
                "exchange": "NSE",
                "currency": "INR",
                "logo": "",
            }

        # Fallback: use last chart candle for indices
        token_info = _resolve_nse_token(clean)
        if token_info:
            history = _fetch_nse_history(
                scripcode=token_info["scripcode"],
                nse_symbol=token_info["symbol"],
                symbol_type=token_info["type"],
                chart_type="D",
                from_ts=int(time.time()) - 10 * 86400,
            )
            if history:
                latest = history[-1]
                prev = history[-2] if len(history) >= 2 else latest
                price = latest["close"]
                prev_close = prev["close"]
                change = price - prev_close
                pct = (change / prev_close * 100) if prev_close else 0
                return {
                    "symbol": symbol,
                    "name": token_info["description"] or clean,
                    "price": round(price, 2),
                    "previousClose": round(prev_close, 2),
                    "change": round(change, 2),
                    "pctChange": round(pct, 2),
                    "open": round(latest.get("open", 0), 2),
                    "dayHigh": round(latest.get("high", 0), 2),
                    "dayLow": round(latest.get("low", 0), 2),
                    "volume": latest.get("volume", 0),
                    "marketCap": 0,
                    "fiftyTwoWeekHigh": 0,
                    "fiftyTwoWeekLow": 0,
                    "exchange": "NSE",
                    "currency": "INR",
                    "logo": "",
                }

        raise HTTPException(status_code=404, detail="Could not resolve symbol")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── History ─────────────────────────────────────────────────────────────────────

@router.get("/history")
async def get_history(
    symbol: str = Query(...),
    period: str = Query("1y"),
    interval: str = Query("1d"),
):
    """Get OHLCV historical data using NSE charting API."""
    try:
        clean = _clean_symbol_for_nse(symbol)
        token_info = _resolve_nse_token(clean)

        if not token_info:
            raise HTTPException(status_code=404, detail=f"Could not resolve symbol: {symbol}")

        # Determine chart type and time interval
        chart_type = "D"  # default daily
        time_interval = 1

        if interval in ("1m",):
            chart_type = "I"
            time_interval = 1
        elif interval in ("5m",):
            chart_type = "I"
            time_interval = 5
        elif interval in ("15m",):
            chart_type = "I"
            time_interval = 15
        elif interval in ("1wk", "5d"):
            chart_type = "W"
        elif interval in ("1mo", "3mo"):
            chart_type = "M"
        # else default to "D" (daily)

        from_ts = _period_to_from_ts(period)

        history = _fetch_nse_history(
            scripcode=token_info["scripcode"],
            nse_symbol=token_info["symbol"],
            symbol_type=token_info["type"],
            chart_type=chart_type,
            time_interval=time_interval,
            from_ts=from_ts,
        )

        data = []
        is_intraday = chart_type == "I"

        for candle in history:
            raw_ts = candle["time"]
            # NSE returns time in milliseconds
            ts_seconds = raw_ts // 1000 if raw_ts > 9999999999 else raw_ts

            if is_intraday:
                # For intraday, use unix timestamp (seconds)
                time_val = ts_seconds
            else:
                # For daily/weekly/monthly, use YYYY-MM-DD string
                dt = datetime.utcfromtimestamp(ts_seconds)
                time_val = dt.strftime("%Y-%m-%d")

            data.append({
                "time": time_val,
                "open": round(candle.get("open", 0), 2),
                "high": round(candle.get("high", 0), 2),
                "low": round(candle.get("low", 0), 2),
                "close": round(candle.get("close", 0), 2),
                "volume": candle.get("volume", 0),
            })

        return {
            "symbol": symbol,
            "history": data,
            "period": period,
            "interval": interval,
            "count": len(data),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Intraday ────────────────────────────────────────────────────────────────────

@router.get("/intraday")
async def get_intraday(
    symbol: str = Query(...),
    interval: str = Query("1m"),
):
    """Get today's intraday data using NSE charting API."""
    try:
        clean = _clean_symbol_for_nse(symbol)
        token_info = _resolve_nse_token(clean)

        if not token_info:
            return {"symbol": symbol, "data": [], "interval": interval}

        time_interval = 1
        if interval == "5m":
            time_interval = 5
        elif interval == "15m":
            time_interval = 15

        now = int(time.time())
        from_ts = now - 86400

        history = _fetch_nse_history(
            scripcode=token_info["scripcode"],
            nse_symbol=token_info["symbol"],
            symbol_type=token_info["type"],
            chart_type="I",
            time_interval=time_interval,
            from_ts=from_ts,
        )

        data = []
        for candle in history:
            raw_ts = candle["time"]
            ts = raw_ts // 1000 if raw_ts > 9999999999 else raw_ts
            data.append({
                "time": ts,
                "open": round(candle.get("open", 0), 2),
                "high": round(candle.get("high", 0), 2),
                "low": round(candle.get("low", 0), 2),
                "close": round(candle.get("close", 0), 2),
                "volume": candle.get("volume", 0),
            })

        return {"symbol": symbol, "data": data, "interval": interval, "count": len(data)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Fundamentals (NSE getSymbolData) ────────────────────────────────────────────

@router.get("/fundamentals")
async def get_fundamentals(symbol: str = Query(...)):
    """Get company fundamentals from NSE getSymbolData."""
    try:
        clean = _clean_symbol_for_nse(symbol)
        data = _nse_quote_api("getSymbolData", {
            "marketType": "N",
            "series": "EQ",
            "symbol": clean,
        })

        if not data or not isinstance(data, dict) or not data.get("equityResponse"):
            raise HTTPException(status_code=404, detail="No data found")

        eq = data["equityResponse"][0]
        meta = eq.get("metaData", {})
        trade = eq.get("tradeInfo", {})
        sec = eq.get("securityInfo", {}) if "securityInfo" in eq else {}
        pe_detail = eq.get("priceInfo", {}) if "priceInfo" in eq else {}

        # Try to enrich with YearwiseData
        year_data = []
        try:
            year_url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getYearwiseData&symbol={clean}EQN"
            r_year = req.get(year_url, headers=NSE_HEADERS, timeout=10)
            year_data = r_year.json()
        except:
            pass
            
        y_data = year_data[0] if isinstance(year_data, list) and len(year_data) > 0 else {}

        return {
            "symbol": clean,
            "name": meta.get("companyName", ""),
            "sector": sec.get("industryInfo", {}).get("industry", "") if isinstance(sec.get("industryInfo"), dict) else "",
            "industry": sec.get("industryInfo", {}).get("basicIndustry", "") if isinstance(sec.get("industryInfo"), dict) else "",
            "marketCap": float(trade.get("ffmc", 0)) / 100000 if trade.get("ffmc") else 0, # rough market cap
            "pe": float(pe_detail.get("pe", 0)) if pe_detail.get("pe", 0) != "-" else 0,
            "forwardPe": 0,
            "eps": float(pe_detail.get("eps", 0)) if pe_detail.get("eps", 0) != "-" else 0,
            "bookValue": float(pe_detail.get("bookValue", 0)) if pe_detail.get("bookValue", 0) else 0,
            "dividendYield": 0,
            "roe": float(y_data.get("one_year_chng_per", 0)) / 100 if y_data.get("one_year_chng_per") else 0, # Map 1yr change to ROE field as placeholder
            "debtToEquity": 0,
            "fiftyTwoWeekHigh": float(sec.get("week52High", 0)) if sec.get("week52High") else 0,
            "fiftyTwoWeekLow": float(sec.get("week52Low", 0)) if sec.get("week52Low") else 0,
            "fiftyDayAvg": 0,
            "twoHundredDayAvg": 0,
            "beta": 0,
            "totalRevenue": 0,
            "revenueGrowth": float(y_data.get("three_year_chng_per", 0)) / 100 if y_data.get("three_year_chng_per") else 0,
            "profitMargin": 0,
            "operatingMargin": 0,
            "website": "",
            "description": "",
            "isin": meta.get("isinCode", ""),
            "series": meta.get("series", ""),
            "listingDate": sec.get("listingDate", "") if sec else "",
        }
    except HTTPException:
        raise
    except Exception as e:
        print("Fundamentals Error:", e)
        raise HTTPException(status_code=400, detail=str(e))


# ─── Financials (NSE getFinancialStatus + getIntegratedFilingData) ────────────────

@router.get("/financials")
async def get_financials(
    symbol: str = Query(...),
    statement: str = Query("results", description="results, filings, annual"),
    quarterly: bool = Query(False),
):
    """Get financial data from NSE APIs."""
    try:
        clean = _clean_symbol_for_nse(symbol)

        if statement == "results":
            data = _nse_quote_api("getFinancialStatus", {"symbol": clean}) or []
            
            # Map NSE raw financials to a table structure for Angular
            formatted_data = {}
            for row in data:
                period = row.get("to_date_MonYr") or row.get("to_date")
                if not period:
                    continue
                
                def _safe_float(val):
                    try:
                        if val is None or val == "": return 0.0
                        return float(val)
                    except:
                        return 0.0
                
                formatted_data[period] = {
                    "Total Income": _safe_float(row.get("totalIncome")) * 100000,
                    "Expenditure": _safe_float(row.get("expenditure")) * 100000,
                    "Net Profit": _safe_float(row.get("prftfAftrTx")) * 100000,
                    "PBDIT": _safe_float(row.get("pbdt")) * 100000,
                    "PBIT": _safe_float(row.get("pbit")) * 100000,
                    "EPS": _safe_float(row.get("dilutedEps")),
                    "Paid Up Capital": _safe_float(row.get("paidUpEqShCap")) * 100000,
                }
            
            return {"symbol": clean, "statement": statement, "data": formatted_data}

        elif statement == "filings":
            data = _nse_quote_api("getIntegratedFilingData", {"symbol": clean})
            return {"symbol": clean, "statement": statement, "data": {}}

        elif statement == "annual":
            data = _nse_quote_api("getCorpAnnualReport", {
                "symbol": clean,
                "marketApiType": "equities",
            })
            return {"symbol": clean, "statement": statement, "data": {}}

        else:
            raise HTTPException(status_code=400, detail="statement must be: results, filings, annual")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── News / Corporate Announcements (NSE getCorporateAnnouncement) ───────────────

@router.get("/news")
async def get_news(symbol: str = Query(...)):
    """Get corporate announcements from NSE."""
    try:
        clean = _clean_symbol_for_nse(symbol)
        today = datetime.now()
        from_date = (today - timedelta(days=365)).strftime("%d-%m-%Y")
        to_date = today.strftime("%d-%m-%Y")

        data = _nse_quote_api("getCorporateAnnouncement", {
            "symbol": clean,
            "marketApiType": "equities",
            "subject": "",
            "fromDate": from_date,
            "toDate": to_date,
        })

        articles = []
        if isinstance(data, list):
            for item in data[:30]:
                articles.append({
                    "title": item.get("desc", ""),
                    "publisher": "NSE",
                    "link": item.get("attchmntFile", "") or item.get("pdfLink", ""),
                    "publishedAt": item.get("an_dt", ""),
                    "thumbnail": "",
                    "subject": item.get("smIndustry", ""),
                    "symbol": item.get("symbol", clean),
                })

        return {"symbol": clean, "articles": articles}
    except Exception:
        return {"symbol": symbol, "articles": []}


# ─── Options (NSE getOptionChainData + getSymbolDerivativesData) ──────────────────

@router.get("/options/dates")
async def get_option_dates(symbol: str = Query(...)):
    """Get available option expiry dates from NSE getOptionChainDropdown."""
    try:
        clean = _clean_symbol_for_nse(symbol)
        
        url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getOptionChainDropdown&symbol={clean}"
        r = req.get(url, headers=NSE_HEADERS, timeout=10)
        data = r.json()

        dates = []
        if isinstance(data, dict):
            dates = data.get("expiryDates", [])
            
        return {"symbol": clean, "dates": dates}
    except Exception as e:
        print("Option Dates Error:", e)
        return {"symbol": symbol, "dates": []}


@router.get("/options/chain")
async def get_option_chain(
    symbol: str = Query(...),
    date: str = Query(..., description="Expiry date in DD-Mon-YYYY format"),
):
    """Get option chain from NSE getOptionChainData."""
    try:
        clean = _clean_symbol_for_nse(symbol)
        
        # User specified endpoint format: params=expiryDate=DD-Mon-YYYY
        url = f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getOptionChainData&symbol={clean}&params=expiryDate={date}"
        r = req.get(url, headers=NSE_HEADERS, timeout=10)
        data = r.json()

        calls = []
        puts = []

        if isinstance(data, dict):
            # The user-provided getOptionChainData returns a top-level 'data' array
            records = data.get("data", [])
            for item in records:
                ce = item.get("CE")
                pe = item.get("PE")

                if ce:
                    calls.append({
                        "strike": float(ce.get("strikePrice", 0)),
                        "lastPrice": float(ce.get("lastPrice", 0)),
                        "change": float(ce.get("change", 0)),
                        "pctChange": float(ce.get("pchange", 0)),  # pchange in this new payload
                        "volume": int(ce.get("totalTradedVolume", 0)),
                        "openInterest": int(ce.get("openInterest", 0)),
                        "impliedVolatility": float(ce.get("impliedVolatility", 0)),
                        "inTheMoney": ce.get("strikePrice", 0) < ce.get("underlyingValue", 0),
                    })

                if pe:
                    puts.append({
                        "strike": float(pe.get("strikePrice", 0)),
                        "lastPrice": float(pe.get("lastPrice", 0)),
                        "change": float(pe.get("change", 0)),
                        "pctChange": float(pe.get("pchange", 0)),  # pchange in this new payload
                        "volume": int(pe.get("totalTradedVolume", 0)),
                        "openInterest": int(pe.get("openInterest", 0)),
                        "impliedVolatility": float(pe.get("impliedVolatility", 0)),
                        "inTheMoney": pe.get("strikePrice", 0) > pe.get("underlyingValue", 0),
                    })

        return {"symbol": clean, "expiryDate": date, "calls": calls, "puts": puts}
    except Exception as e:
        print("Option chain error:", e)
        return {"symbol": symbol, "expiryDate": date, "calls": [], "puts": []}


# ─── Derivatives Summary ─────────────────────────────────────────────────────────

@router.get("/derivatives")
async def get_derivatives(symbol: str = Query(...)):
    """Get derivatives summary from NSE getSymbolDerivativesData."""
    try:
        clean = _clean_symbol_for_nse(symbol)
        data = _nse_quote_api("getSymbolDerivativesData", {"symbol": clean})
        return {"symbol": clean, "data": data}
    except Exception:
        return {"symbol": symbol, "data": None}
