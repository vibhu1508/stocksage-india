"""
NSE Platform Backend - Main Application
FastAPI server with Google OAuth and SQLite database
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import routers
from routers import auth, stocks, fo_analysis, announcements, market_data, learn, strategy_builder
from database import engine, Base

# Create database tables on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create database tables
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown: cleanup if needed

app = FastAPI(
    title="NSE Platform API",
    description="Backend API for NSE Stock Analysis Platform",
    version="1.0.0",
    lifespan=lifespan
)

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
secret_key = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
app.add_middleware(SessionMiddleware, secret_key=secret_key)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["Stock Comparison"])
app.include_router(fo_analysis.router, prefix="/api/fo", tags=["F&O Analysis"])
app.include_router(announcements.router, prefix="/api/announcements", tags=["Announcements"])
app.include_router(learn.router, prefix="/api/learn", tags=["Learn"])
app.include_router(strategy_builder.router, prefix="/api/strategy", tags=["Strategy Builder"])
app.include_router(market_data.router, prefix="/api/market", tags=["Market Data"])
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
