"""
Tools the StockSage AI assistant can call. Each wraps existing backend logic so
the model works only with our own real data (never invents numbers).

Read-only, public market data for now; portfolio writes come later (behind auth +
confirmation).
"""

import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

_IST = timezone(timedelta(hours=5, minutes=30))

from routers import market_data as md
from routers import dhan_market as dm
from routers.announcements import fetch_nse_announcements
from routers.strategy_builder import nse_session
from services import portfolio_actions as pa
from services import news as news_service

logger = logging.getLogger(__name__)

# OpenAI-style function schemas advertised to the model.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_market_overview",
            "description": "Live snapshot of Indian indices (NIFTY 50, SENSEX, BANKNIFTY, etc.) and whether the market is open. Use for 'how is the market today', 'what's Nifty at'.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_movers",
            "description": "Today's top gaining or losing stocks on NSE.",
            "parameters": {
                "type": "object",
                "properties": {"direction": {"type": "string", "enum": ["gainers", "losers"]}},
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "Live / last-traded price of a single NSE stock by symbol (e.g. RELIANCE, TCS, AXISBANK).",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "NSE symbol"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_announcements",
            "description": "Recent NSE corporate announcements / filings for a stock symbol (results, dividends, board meetings, etc.).",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "NSE symbol"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_quote",
            "description": "Detailed quote for one NSE stock: company name, day's high/low, open, previous close, change, percent change today, and traded volume. Use for the day's high/low, today's % change, or volume.",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "NSE symbol"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_52_week_range",
            "description": "The 52-week (1-year) high and low for one NSE stock, plus its latest price. Use for '52 week high/low' questions.",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "NSE symbol"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_on_date",
            "description": "Closing price of one NSE stock on a specific PAST date, plus the percent change from that date to the latest close. Use for 'price on <date>' or '% change/jump since <date>'. Give the day and month; include year ONLY if the user explicitly stated one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "NSE symbol"},
                    "day": {"type": "integer", "description": "Day of month, 1-31"},
                    "month": {"type": "integer", "description": "Month, 1-12"},
                    "year": {"type": "integer", "description": "4-digit year — OMIT unless the user explicitly gave a year"},
                },
                "required": ["symbol", "day", "month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio",
            "description": "The signed-in user's own portfolio holdings. Use when the user asks about 'my portfolio', 'my holdings', 'my stocks'.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_holding",
            "description": "Record a stock the USER decided to add to THEIR OWN portfolio (bookkeeping, not advice). Use when the user says things like 'add/record X to my portfolio', 'main ne X kharida'. Needs symbol, quantity, and average buy price — if any are missing, ask the user for them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "NSE symbol"},
                    "quantity": {"type": "integer", "description": "Number of shares"},
                    "avg_price": {"type": "number", "description": "Average buy price per share"},
                },
                "required": ["symbol", "quantity", "avg_price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Latest news from trusted sources (MoneyControl, Times of India, Rediff, etc.) for a specific stock, or general Indian market news if no symbol is given.",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "NSE symbol (optional; omit for general market news)"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sentiment",
            "description": "A neutral, market-aware read on a stock: recent trusted-source news, today's index trend, and the stock's % change today. Use for 'sentiment', 'news', 'mahaul', 'khabar kaisi hai'.",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "NSE symbol"}},
                "required": ["symbol"],
            },
        },
    },
]


async def _market_overview() -> Dict[str, Any]:
    d = await md.get_indices()
    return {
        "market_status": d.get("market_status"),
        "indices": [
            {"symbol": i.get("symbol"), "value": i.get("value"), "pct_change": i.get("pct_change")}
            for i in (d.get("indices") or [])[:8]
        ],
    }


async def _top_movers(direction: str) -> Dict[str, Any]:
    if str(direction).lower() == "losers":
        d = await md.get_top_losers()
        items = d.get("losers") or []
    else:
        direction = "gainers"
        d = await md.get_top_stocks()
        items = d.get("gainers") or []
    return {
        "direction": direction,
        "stocks": [
            {"symbol": s.get("symbol"), "price": s.get("price"), "pct_change": s.get("pct_change")}
            for s in items[:10]
        ],
    }


async def _stock_price(symbol: str) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"error": "no symbol provided"}
    try:
        # Pass every arg explicitly so FastAPI Query defaults don't leak through.
        r = await dm.dhan_chart_latest(
            symbol=sym, timeframe="5", securityId=None, exchangeSegment=None, instrument=None
        )
        return {"symbol": sym, "price": r.get("price"), "source": r.get("source")}
    except Exception:
        logger.exception("get_stock_price failed for %s", sym)
        return {"symbol": sym, "error": "price unavailable right now"}


async def _announcements(symbol: str) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"error": "no symbol provided"}
    # fetch_nse_announcements is synchronous/blocking — run off the event loop.
    anns = await asyncio.to_thread(fetch_nse_announcements, sym, None, None, 5)
    return {
        "symbol": sym,
        "announcements": [
            {"subject": a.get("subject"), "date": a.get("broadcast_date"), "category": a.get("category")}
            for a in (anns or [])[:5]
        ],
    }


async def _stock_quote(symbol: str) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"error": "no symbol provided"}
    url = (
        "https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi"
        f"?functionName=getSymbolData&marketType=N&series=EQ&symbol={sym}"
    )
    try:
        data = await nse_session.get_data(url)
    except Exception:
        logger.exception("get_stock_quote failed for %s", sym)
        return {"symbol": sym, "error": "quote unavailable right now"}
    er = (data.get("equityResponse") or [{}])[0] if isinstance(data, dict) else {}
    meta = er.get("metaData") or {}
    trade = er.get("tradeInfo") or {}
    return {
        "symbol": sym,
        "company": meta.get("companyName"),
        "last_price": (er.get("orderBook") or {}).get("lastPrice") or meta.get("closePrice"),
        "open": meta.get("open"),
        "day_high": meta.get("dayHigh"),
        "day_low": meta.get("dayLow"),
        "previous_close": meta.get("previousClose"),
        "change": meta.get("change"),
        "pct_change": meta.get("pChange"),
        "volume": trade.get("totalTradedVolume"),
    }


async def _daily_candles(symbol: str) -> list[dict]:
    """Full daily-candle history for a symbol via Dhan (ascending by time)."""
    identity = await dm._resolve_chart_identity(symbol.upper(), None, None, None)
    payload = dm._build_daily_historical_payload(identity)
    resp = await dm._cached_dhan_post("/charts/historical", payload, "history")
    return dm._to_lightweight_candles(resp.get("data") or {})


async def _52_week_range(symbol: str) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"error": "no symbol provided"}
    try:
        candles = await _daily_candles(sym)
    except Exception:
        logger.exception("get_52_week_range failed for %s", sym)
        return {"symbol": sym, "error": "historical data unavailable"}
    if not candles:
        return {"symbol": sym, "error": "no historical data"}
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    cutoff = now_epoch - 365 * 86400
    recent = [c for c in candles if int(c["time"]) >= cutoff] or candles[-252:]
    return {
        "symbol": sym,
        "week52_high": round(max(float(c["high"]) for c in recent), 2),
        "week52_low": round(min(float(c["low"]) for c in recent), 2),
        "latest_close": round(float(candles[-1]["close"]), 2),
    }


def _parse_date(value: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


async def _price_on_date(symbol: str, day, month, year=None) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"error": "no symbol provided"}
    try:
        day_i, month_i = int(day), int(month)
    except (TypeError, ValueError):
        return {"symbol": sym, "error": "invalid day/month"}
    today = datetime.now(_IST).date()
    try:
        if year:
            target = date(int(year), month_i, day_i)
        else:
            # Most recent PAST occurrence of this day/month.
            candidate = date(today.year, month_i, day_i)
            target = candidate if candidate <= today else date(today.year - 1, month_i, day_i)
    except ValueError:
        return {"symbol": sym, "error": "invalid date"}
    try:
        candles = await _daily_candles(sym)
    except Exception:
        logger.exception("get_price_on_date failed for %s", sym)
        return {"symbol": sym, "error": "historical data unavailable"}
    if not candles:
        return {"symbol": sym, "error": "no historical data"}
    # Nearest trading day on or before the target date.
    chosen = None
    for c in candles:
        if dm._ist_date_from_epoch(int(c["time"])) <= target:
            chosen = c
        else:
            break
    if not chosen:
        return {"symbol": sym, "error": f"no data on or before {target.isoformat()}"}
    on_close = round(float(chosen["close"]), 2)
    latest_close = round(float(candles[-1]["close"]), 2)
    pct = round((latest_close - on_close) / on_close * 100, 2) if on_close else None
    return {
        "symbol": sym,
        "requested_date": target.isoformat(),
        "actual_date": dm._ist_date_from_epoch(int(chosen["time"])).isoformat(),
        "close_on_date": on_close,
        "latest_close": latest_close,
        "pct_change_since": pct,
    }


async def _get_portfolio(user_id: Optional[int]) -> Dict[str, Any]:
    if not user_id:
        return {"error": "Please sign in to view your portfolio."}
    holdings = await asyncio.to_thread(pa.get_user_holdings, user_id)
    return {"holdings": holdings, "count": len(holdings)}


async def _record_holding(user_id: Optional[int], symbol, quantity, avg_price) -> Dict[str, Any]:
    """Does NOT write — returns a confirmation request. The agent confirms with the user
    and the actual write happens only after they click Confirm."""
    if not user_id:
        return {"error": "Please sign in to modify your portfolio."}
    sym = str(symbol or "").strip().upper()
    try:
        qty = int(quantity)
    except (TypeError, ValueError):
        qty = None
    try:
        price = float(avg_price)
    except (TypeError, ValueError):
        price = None
    if not sym or not qty or qty <= 0 or not price or price <= 0:
        return {"status": "need_info", "message": "Ask the user for the stock symbol, quantity, and average buy price."}
    return {"status": "needs_confirmation", "symbol": sym, "quantity": qty, "avg_price": price}


async def _news(symbol: Optional[str] = None) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    query = f"{sym} share stock NSE India" if sym else "Indian stock market Sensex Nifty today"
    items = await news_service.fetch_trusted_news(query, limit=6)
    return {"topic": sym or "market", "news": items}


async def _sentiment(symbol: str) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"error": "no symbol provided"}
    news = await news_service.fetch_trusted_news(f"{sym} share stock NSE India", limit=5)
    try:
        overview = await md.get_indices()
    except Exception:
        overview = {}
    quote = await _stock_quote(sym)
    return {
        "symbol": sym,
        "recent_news": news,
        "market_status": overview.get("market_status") if isinstance(overview, dict) else None,
        "index_trend": [
            {"symbol": i.get("symbol"), "pct_change": i.get("pct_change")}
            for i in (overview.get("indices") or [])[:3]
        ] if isinstance(overview, dict) else [],
        "stock_pct_change_today": quote.get("pct_change") if isinstance(quote, dict) else None,
    }


async def execute_tool(name: str, args_json: str, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Dispatch a tool call; always returns a JSON-serializable dict."""
    try:
        args = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError:
        args = {}

    try:
        if name == "get_market_overview":
            return await _market_overview()
        if name == "get_top_movers":
            return await _top_movers(args.get("direction", "gainers"))
        if name == "get_stock_price":
            return await _stock_price(args.get("symbol", ""))
        if name == "get_announcements":
            return await _announcements(args.get("symbol", ""))
        if name == "get_stock_quote":
            return await _stock_quote(args.get("symbol", ""))
        if name == "get_52_week_range":
            return await _52_week_range(args.get("symbol", ""))
        if name == "get_price_on_date":
            return await _price_on_date(
                args.get("symbol", ""), args.get("day"), args.get("month"), args.get("year")
            )
        if name == "get_portfolio":
            return await _get_portfolio(user_id)
        if name == "record_holding":
            return await _record_holding(
                user_id, args.get("symbol"), args.get("quantity"), args.get("avg_price")
            )
        if name == "get_news":
            return await _news(args.get("symbol"))
        if name == "get_sentiment":
            return await _sentiment(args.get("symbol", ""))
        return {"error": f"unknown tool: {name}"}
    except Exception as exc:
        logger.exception("tool %s failed", name)
        return {"error": "tool failed", "detail": str(exc)[:200]}
