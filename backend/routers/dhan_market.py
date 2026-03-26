"""
Dhan Market Data Router - centralized proxy endpoints for Dhan v2 APIs.

The design is cache-first and shared across users so backend fetches are reused.
"""

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional, Union
import asyncio
import hashlib
import json
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from routers.auth import get_current_user
from models import User
from services.redis_store import (
    cache_get_json,
    cache_set_json,
    close_pubsub,
    create_pubsub,
    is_rate_limited,
    ping_redis,
    publish_json,
)

router = APIRouter()

DHAN_BASE_URL = "https://api.dhan.co/v2"
RATE_LIMIT_PER_MINUTE = int(os.getenv("DHAN_RATE_LIMIT_PER_MINUTE", "60"))
STREAM_CHANNEL_PREFIX = os.getenv("MARKET_STREAM_CHANNEL_PREFIX", "market").strip() or "market"


def _cache_ttls() -> dict:
    return {
        "quote": int(os.getenv("DHAN_CACHE_TTL_QUOTE", "3")),
        "options": int(os.getenv("DHAN_CACHE_TTL_OPTIONS", "3")),
        "history": int(os.getenv("DHAN_CACHE_TTL_HISTORY", "60")),
    }


def _get_dhan_headers() -> Dict[str, str]:
    access_token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()

    if not access_token or not client_id:
        raise HTTPException(
            status_code=500,
            detail="Dhan credentials are not configured. Set DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID.",
        )

    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "access-token": access_token,
        "client-id": client_id,
    }


async def _dhan_post(endpoint: str, payload: dict) -> dict:
    url = f"{DHAN_BASE_URL}{endpoint}"
    headers = _get_dhan_headers()

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = "Dhan API request failed"
        try:
            body = exc.response.json()
            if isinstance(body, dict) and body.get("remarks"):
                detail = str(body.get("remarks"))
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=detail)
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Unable to reach Dhan API")


def _cache_key(prefix: str, endpoint: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{endpoint}|{canonical}".encode()).hexdigest()
    return f"dhan:{prefix}:{digest}"


async def _cached_dhan_post(endpoint: str, payload: dict, bucket: str) -> dict:
    ttl = max(1, _cache_ttls().get(bucket, 3))
    key = _cache_key(bucket, endpoint, payload)

    cached = await cache_get_json(key)
    if cached is not None:
        return {"source": "cache", "data": cached}

    global_limit_key = f"dhan:rl:{bucket}"
    if await is_rate_limited(global_limit_key, RATE_LIMIT_PER_MINUTE, 60):
        raise HTTPException(status_code=429, detail="Rate limit reached for market data. Please retry shortly.")

    live = await _dhan_post(endpoint, payload)
    await cache_set_json(key, live, ttl)
    await publish_json(
        f"{STREAM_CHANNEL_PREFIX}:{bucket}",
        {
            "bucket": bucket,
            "endpoint": endpoint,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": live,
        },
    )
    return {"source": "live", "data": live}


class SecuritiesRequest(BaseModel):
    securities: Dict[str, List[Union[int, str]]] = Field(
        ...,
        example={"NSE_EQ": [1333], "NSE_FNO": [49081, 49082]},
    )


class HistoricalDailyRequest(BaseModel):
    securityId: Union[int, str]
    exchangeSegment: str
    instrument: str
    fromDate: str
    toDate: str
    expiryCode: int = 0
    oi: bool = False


class HistoricalIntradayRequest(BaseModel):
    securityId: Union[int, str]
    exchangeSegment: str
    instrument: str
    interval: int = 1
    fromDate: str
    toDate: str
    oi: bool = False


class OptionChainRequest(BaseModel):
    UnderlyingScrip: int
    UnderlyingSeg: str
    Expiry: str


class ExpiryListRequest(BaseModel):
    UnderlyingScrip: int
    UnderlyingSeg: str


class ExpiredOptionsRequest(BaseModel):
    exchangeSegment: str
    interval: int = 1
    securityId: Union[int, str]
    instrument: str
    expiryFlag: str
    expiryCode: int
    strike: str
    drvOptionType: str
    requiredData: List[str]
    fromDate: str
    toDate: str


class CacheWarmJob(BaseModel):
    bucket: Literal["quote", "options", "history"]
    endpoint: str
    payload: dict


class CacheWarmRequest(BaseModel):
    jobs: List[CacheWarmJob] = Field(default_factory=list)


class StreamPublishRequest(BaseModel):
    bucket: Literal["quote", "options", "history", "broadcast"]
    event: str = "market_update"
    data: dict
    symbol: Optional[str] = None


ALLOWED_WARM_ENDPOINTS = {
    "quote": {"/marketfeed/ltp", "/marketfeed/ohlc", "/marketfeed/quote"},
    "options": {"/optionchain", "/optionchain/expirylist"},
    "history": {"/charts/historical", "/charts/intraday", "/charts/rollingoption"},
}


def _stream_channel(bucket: str) -> str:
    return f"{STREAM_CHANNEL_PREFIX}:{bucket}"


@router.get("/status")
async def dhan_status():
    configured = bool(os.getenv("DHAN_ACCESS_TOKEN")) and bool(os.getenv("DHAN_CLIENT_ID"))
    redis_ok = await ping_redis()
    return {"configured": configured, "redis_connected": redis_ok}


@router.post("/quote/ltp")
async def dhan_ltp_quote(
    payload: SecuritiesRequest,
):
    return await _cached_dhan_post("/marketfeed/ltp", payload.securities, "quote")


@router.post("/quote/ohlc")
async def dhan_ohlc_quote(
    payload: SecuritiesRequest,
):
    return await _cached_dhan_post("/marketfeed/ohlc", payload.securities, "quote")


@router.post("/quote/full")
async def dhan_full_quote(
    payload: SecuritiesRequest,
):
    return await _cached_dhan_post("/marketfeed/quote", payload.securities, "quote")


@router.post("/historical/daily")
async def dhan_historical_daily(
    payload: HistoricalDailyRequest,
):
    return await _cached_dhan_post("/charts/historical", payload.model_dump(), "history")


@router.post("/historical/intraday")
async def dhan_historical_intraday(
    payload: HistoricalIntradayRequest,
):
    return await _cached_dhan_post("/charts/intraday", payload.model_dump(), "history")


@router.post("/options/chain")
async def dhan_option_chain(
    payload: OptionChainRequest,
):
    return await _cached_dhan_post("/optionchain", payload.model_dump(), "options")


@router.post("/options/expiry-list")
async def dhan_expiry_list(
    payload: ExpiryListRequest,
):
    return await _cached_dhan_post("/optionchain/expirylist", payload.model_dump(), "options")


@router.post("/options/expired-rolling")
async def dhan_expired_rolling_options(
    payload: ExpiredOptionsRequest,
):
    return await _cached_dhan_post("/charts/rollingoption", payload.model_dump(), "history")


@router.post("/cache/warm")
async def warm_market_cache(
    payload: CacheWarmRequest,
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admin users can warm the shared cache")

    if not payload.jobs:
        return {"warmed": 0, "results": []}

    if len(payload.jobs) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 warm jobs per request")

    results = []
    for index, job in enumerate(payload.jobs):
        if job.endpoint not in ALLOWED_WARM_ENDPOINTS.get(job.bucket, set()):
            results.append(
                {
                    "index": index,
                    "bucket": job.bucket,
                    "endpoint": job.endpoint,
                    "ok": False,
                    "error": "Endpoint is not allowed for this bucket",
                }
            )
            continue

        try:
            response = await _cached_dhan_post(job.endpoint, job.payload, job.bucket)
            results.append(
                {
                    "index": index,
                    "bucket": job.bucket,
                    "endpoint": job.endpoint,
                    "ok": True,
                    "source": response.get("source"),
                }
            )
        except HTTPException as exc:
            results.append(
                {
                    "index": index,
                    "bucket": job.bucket,
                    "endpoint": job.endpoint,
                    "ok": False,
                    "error": exc.detail,
                }
            )

    warmed = sum(1 for r in results if r.get("ok"))
    return {"warmed": warmed, "total": len(results), "results": results}


@router.post("/stream/publish")
async def publish_market_event(
    payload: StreamPublishRequest,
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admin users can publish stream events")

    channel = _stream_channel(payload.bucket)
    published = await publish_json(
        channel,
        {
            "event": payload.event,
            "symbol": payload.symbol,
            "bucket": payload.bucket,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": payload.data,
        },
    )
    if not published:
        raise HTTPException(status_code=503, detail="Redis pub/sub is unavailable")

    return {"published": True, "channel": channel}


@router.websocket("/stream/ws")
async def market_stream_ws(websocket: WebSocket):
    requested = websocket.query_params.get("channels", "quote,options,history,broadcast")
    channels = []
    for raw in requested.split(","):
        name = raw.strip()
        if not name:
            continue
        channels.append(_stream_channel(name))

    channels = list(dict.fromkeys(channels))
    await websocket.accept()

    if not channels:
        await websocket.send_json({"error": "No channels requested"})
        await websocket.close(code=1008)
        return

    pubsub = await create_pubsub(channels)
    if pubsub is None:
        await websocket.send_json({"error": "Redis pub/sub unavailable"})
        await websocket.close(code=1013)
        return

    await websocket.send_json({"event": "subscribed", "channels": channels})

    heartbeat_every = 15
    idle_ticks = 0

    try:
        while True:
            message = await pubsub.get_message(timeout=1.0)
            if message and message.get("type") == "message":
                idle_ticks = 0
                data = message.get("data")
                if isinstance(data, str):
                    try:
                        await websocket.send_json(json.loads(data))
                    except json.JSONDecodeError:
                        await websocket.send_json({"event": "raw", "data": data})
                else:
                    await websocket.send_json({"event": "raw", "data": data})
            else:
                idle_ticks += 1
                if idle_ticks >= heartbeat_every:
                    idle_ticks = 0
                    await websocket.send_json(
                        {
                            "event": "heartbeat",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        return
    finally:
        await close_pubsub(pubsub, channels)
