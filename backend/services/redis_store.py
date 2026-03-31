"""
Redis helper service for cache, rate limiting, and token revocation.

All functions degrade gracefully when Redis is not configured.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError

_redis_client: Optional[Redis] = None


def _prefix() -> str:
    return os.getenv("REDIS_PREFIX", "stocksage").strip() or "stocksage"


def _redis_url() -> str:
    return os.getenv("REDIS_URL", "").strip()


def _key(raw: str) -> str:
    return f"{_prefix()}:{raw}"


def get_redis_client() -> Optional[Redis]:
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    url = _redis_url()
    if not url:
        return None

    _redis_client = Redis.from_url(url, decode_responses=True)
    return _redis_client


async def ping_redis() -> bool:
    client = get_redis_client()
    if client is None:
        return False
    try:
        return bool(await client.ping())
    except RedisError:
        return False


async def close_redis() -> None:
    global _redis_client
    if _redis_client is None:
        return
    try:
        await _redis_client.close()
    except RedisError:
        pass
    _redis_client = None


async def cache_get_json(raw_key: str) -> Optional[Any]:
    client = get_redis_client()
    if client is None:
        return None
    try:
        value = await client.get(_key(raw_key))
        if value is None:
            return None
        return json.loads(value)
    except (RedisError, json.JSONDecodeError):
        return None


async def cache_set_json(raw_key: str, value: Any, ttl_seconds: int) -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        await client.set(_key(raw_key), json.dumps(value), ex=max(1, ttl_seconds))
    except (RedisError, TypeError):
        return


def _coerce_counter(value: Any) -> int:
    """Normalize Redis counter responses to an integer.

    Some Redis client/proxy setups can return wrapped values (for example,
    single-item lists). This keeps rate-limit comparisons stable.
    """
    if isinstance(value, int):
        return value
    if isinstance(value, (bytes, str)):
        return int(value)
    if isinstance(value, list):
        if not value:
            return 0
        return _coerce_counter(value[-1])
    return int(value)


async def is_rate_limited(raw_key: str, limit: int, window_seconds: int) -> bool:
    client = get_redis_client()
    if client is None:
        return False

    key = _key(raw_key)
    try:
        current_raw = await client.incr(key)
        current = _coerce_counter(current_raw)
        if current == 1:
            await client.expire(key, max(1, window_seconds))
        return current > max(1, limit)
    except (RedisError, ValueError, TypeError):
        return False


async def revoke_token(token_hash: str, ttl_seconds: int) -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        await client.set(_key(f"jwt:revoked:{token_hash}"), "1", ex=max(1, ttl_seconds))
    except RedisError:
        return


async def is_token_revoked(token_hash: str) -> bool:
    client = get_redis_client()
    if client is None:
        return False
    try:
        return bool(await client.exists(_key(f"jwt:revoked:{token_hash}")))
    except RedisError:
        return False


async def publish_json(raw_channel: str, value: Any) -> bool:
    client = get_redis_client()
    if client is None:
        return False
    try:
        payload = json.dumps(value)
        await client.publish(_key(raw_channel), payload)
        return True
    except (RedisError, TypeError):
        return False


def prefixed_channel(raw_channel: str) -> str:
    return _key(raw_channel)


async def create_pubsub(channels: list[str]) -> Optional[PubSub]:
    client = get_redis_client()
    if client is None:
        return None
    if not channels:
        return None
    try:
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(*[prefixed_channel(ch) for ch in channels])
        return pubsub
    except RedisError:
        return None


async def close_pubsub(pubsub: Optional[PubSub], channels: list[str]) -> None:
    if pubsub is None:
        return
    try:
        if channels:
            await pubsub.unsubscribe(*[prefixed_channel(ch) for ch in channels])
        await pubsub.close()
    except RedisError:
        return
