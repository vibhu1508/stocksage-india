"""
NSE Platform Backend - Main Application
FastAPI server with Google OAuth and SQLite database
"""

import logging

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
