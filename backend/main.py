"""
NSE Platform Backend - Main Application
FastAPI server with Google OAuth and SQLite database
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import inspect, text
import os
from dotenv import load_dotenv
from services.redis_store import close_redis

# Load environment variables
load_dotenv()

# Import routers
from routers import auth, stocks, fo_analysis, announcements, market_data, learn, strategy_builder, portfolio, dhan_market, chat
from services.instruments import get_instruments
from database import engine, Base


def _ensure_user_onboarding_columns():
    """Backfill newly added users table columns for existing SQLite/PostgreSQL DBs."""
    required = {
        "phone": "VARCHAR(20)",
        "address": "TEXT",
        "occupation": "VARCHAR(100)",
        "trading_experience": "VARCHAR(50)",
        "onboarding_completed": "BOOLEAN DEFAULT FALSE",
        "onboarding_skipped": "BOOLEAN DEFAULT FALSE",
    }

    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("users")}
    missing = [(name, col_type) for name, col_type in required.items() if name not in existing]

    if not missing:
        return

    with engine.begin() as conn:
        for col_name, col_type in missing:
            conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))

# Create database tables on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create database tables
    Base.metadata.create_all(bind=engine)
    _ensure_user_onboarding_columns()
    # Load the stock list now, so the first search after a restart doesn't wait for it.
    app.state.instruments_warmup = asyncio.create_task(get_instruments())
    yield
    # Shutdown: cleanup if needed
    await close_redis()

app = FastAPI(
    title="NSE Platform API",
    description="Backend API for NSE Stock Analysis Platform",
    version="1.0.0",
    lifespan=lifespan
)

# Server-side failures (5xx) never show their detail to users: it can name a data provider, carry an
# upstream URL or an exception message. The full detail is logged; the client gets a neutral message
# with the same status code. Client errors (4xx) keep their message.
@app.exception_handler(StarletteHTTPException)
async def hide_server_error_details(request: Request, exc: StarletteHTTPException):
    if exc.status_code >= 500:
        logging.getLogger("api.errors").warning("%s %s -> %s: %s", request.method, request.url.path, exc.status_code, exc.detail)
        return JSONResponse({"detail": "Internal server error. Please try again shortly."}, status_code=exc.status_code, headers=exc.headers)
    return await http_exception_handler(request, exc)



# Browser caching for shared market data (the same for every user, so a reload needn't re-download
# it). "private": only the user's own browser keeps it. Data about a date that has passed never
# changes, so it is kept a day. Personal data (portfolio, account, chat) is never stored.
_CACHE_RULES = (  # (path prefix, seconds, seconds when every date asked for is in the past)
    ("/api/market/top-stocks", 30, 30),
    ("/api/market/top-losers", 30, 30),
    ("/api/stocks/search", 300, 300),
    ("/api/stocks/index/", 60, 60),
    ("/api/strategy/yearwise-data/", 3600, 3600),
    ("/api/stocks/bhavcopy/", 300, 86400),
    ("/api/stocks/compare", 300, 86400),
    ("/api/fo/data/", 300, 86400),
)
_NO_STORE = ("/api/portfolio", "/api/auth", "/api/chat")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def cache_control_for(path: str, query: str, today: str) -> Optional[str]:
    if path.startswith(_NO_STORE):
        return "no-store"
    for prefix, seconds, past_seconds in _CACHE_RULES:
        if path.startswith(prefix):
            dates = _DATE.findall(path + "?" + query)
            return f"private, max-age={past_seconds if dates and max(dates) < today else seconds}"
    return None


@app.middleware("http")
async def browser_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if (request.method == "GET" and response.status_code == 200 and "cache-control" not in response.headers
            and "set-cookie" not in response.headers):
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
        value = cache_control_for(request.url.path, request.url.query, today)
        if value:
            response.headers["Cache-Control"] = value
    return response


# CORS configuration
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:4200").rstrip("/")

# Ensure it includes the custom domain and common variants
allowed_origins = [
    frontend_url,
    "https://stocksageindia.tech",
    "https://www.stocksageindia.tech",
    "http://localhost:4200"
]

# Ensure no empty strings or duplicates
allowed_origins = [o for o in allowed_origins if o]
allowed_origins = list(set(allowed_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Session middleware for OAuth (required by Authlib)
from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key=auth.SECRET_KEY)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["Stock Comparison"])
app.include_router(fo_analysis.router, prefix="/api/fo", tags=["F&O Analysis"])
app.include_router(announcements.router, prefix="/api/announcements", tags=["Announcements"])
app.include_router(learn.router, prefix="/api/learn", tags=["Learn"])
app.include_router(strategy_builder.router, prefix="/api/strategy", tags=["Strategy Builder"])
app.include_router(market_data.router, prefix="/api/market", tags=["Market Data"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(dhan_market.router, prefix="/api/market/dhan", tags=["Dhan Market Data"])
app.include_router(chat.router, prefix="/api/chat", tags=["AI Assistant"])
@app.get("/")
async def root():
    return {
        "message": "NSE Platform API",
        "docs": "/docs",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
