"""
Market service (plan §4.5, §5.2–5.4): the live-data path for charts.

- Ingest: one Dhan feed connection for every watched symbol. Builds 1-minute candles
  and writes them to Redis.
- Gateway: one WebSocket per browser. Sends a snapshot (about a week of candles) when a
  chart subscribes, then deltas as ticks arrive. Higher timeframes are rolled up from 1m.

Both share one process for the pilot and talk only through Redis keys and channels, so
they can run as separate services later. Run from backend/:
    python -m market.service          # listens on MARKET_PORT (default 8001)
"""

import asyncio
import json
import logging
import os
import random
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import parse_qs, urlsplit

import websockets
from dotenv import load_dotenv

load_dotenv()

from fastapi import HTTPException  # noqa: E402

from market.candles import IST, CandleBuilder, aggregate, bucket_start  # noqa: E402
from market.feed import FATAL_DISCONNECT, feed_url, iter_packets, parse_packet, subscribe_frames  # noqa: E402
from routers import dhan_market as dm  # noqa: E402
from services.redis_store import _key as rkey, get_redis_client  # noqa: E402
from utils.market_utils import is_market_holiday  # noqa: E402

logger = logging.getLogger("market.service")

HISTORY_DAYS = int(os.getenv("MARKET_HISTORY_DAYS", "7"))  # calendar days of 1m history, about 5 sessions
CANDLE_TTL = 9 * 86400
MAX_SNAPSHOT = 3000
STALE_TICK_SECONDS = 120  # ignore quotes whose last trade is older: a resend of an old trade, not a new one
TIMEFRAMES = {"1": 1, "5": 5, "15": 15, "25": 25, "60": 60}
INSTRUMENTS = "market:instruments"
SUBSCRIBE_CHANNEL = "market:subscribe"
FEED_SEEN = "market:feed_seen"  # last time ingest received any packet
FEED_ALIVE_SECONDS = 30


class FatalFeedError(RuntimeError):
    """Dhan refused the feed for a reason a retry with the same token cannot fix."""


def _m1_key(sid: str) -> str:
    return rkey(f"m1:{sid}")


async def load_m1(redis, sid: str) -> list[list]:
    raw = await redis.hgetall(_m1_key(sid))
    return sorted((json.loads(v) for v in raw.values()), key=lambda c: c[0])


async def market_state() -> str:
    now = datetime.now(IST)
    if await asyncio.to_thread(is_market_holiday, now.date()):
        return "closed"
    minute = now.hour * 60 + now.minute
    return "open" if 9 * 60 + 15 <= minute < 15 * 60 + 30 else "closed"


async def request_feed(redis, ident: dict) -> None:
    """Ask ingest to stream this instrument (idempotent). Used by the gateway and by REST
    readers such as the portfolio, which then read `quote:{sid}`."""
    sid = str(ident["securityId"])
    await redis.hset(rkey(INSTRUMENTS), sid, ident["exchangeSegment"])
    await redis.publish(rkey(SUBSCRIBE_CHANNEL), json.dumps({"sid": sid, "segment": ident["exchangeSegment"]}))


async def feed_alive(redis) -> bool:
    """True when ingest received a packet in the last FEED_ALIVE_SECONDS (any symbol)."""
    seen = await redis.get(rkey(FEED_SEEN))
    return bool(seen) and float(seen) >= time.time() - FEED_ALIVE_SECONDS


async def feed_quote(redis, ident: dict) -> Optional[dict]:
    """Latest feed price for an instrument as {price, ts}, or None if the feed hasn't seen one yet."""
    quote = await redis.hgetall(rkey(f"quote:{ident['securityId']}"))
    if not (quote.get("price") and quote.get("ts")):
        return None
    return {"price": float(quote["price"]), "ts": int(quote["ts"])}


def _history_candles(data: dict) -> list[list]:
    """Dhan intraday arrays -> [[t, o, h, l, c, v], ...], keeping volume."""
    cols = [data.get(k) or [] for k in ("timestamp", "open", "high", "low", "close", "volume")]
    return [[int(t), float(o), float(h), float(l), float(c), int(v or 0)] for t, o, h, l, c, v in zip(*cols)]


_seed_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def ensure_seeded(redis, ident: dict) -> None:
    """Load about a week of 1-minute history once per symbol per day (plan §5.2 step 7)."""
    sid = str(ident["securityId"])
    today = datetime.now(IST).date().isoformat()
    async with _seed_locks[sid]:
        if await redis.get(rkey(f"seeded:{sid}")) == today:
            return
        now = datetime.now(IST)
        payload = {
            "securityId": sid, "exchangeSegment": ident["exchangeSegment"], "instrument": ident["instrument"],
            "interval": 1, "oi": False,
            "fromDate": (now - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d 09:15:00"),
            "toDate": now.strftime("%Y-%m-%d %H:%M:%S"),
        }
        resp = await dm._cached_dhan_post("/charts/intraday", payload, "history")
        candles = _history_candles(resp.get("data") or {})
        async with redis.pipeline(transaction=True) as pipe:
            pipe.delete(_m1_key(sid))
            if candles:
                pipe.hset(_m1_key(sid), mapping={str(c[0]): json.dumps(c) for c in candles})
                pipe.expire(_m1_key(sid), CANDLE_TTL)
            pipe.set(rkey(f"seeded:{sid}"), today, ex=86400)
            await pipe.execute()
        logger.info("seeded %s (%s): %d one-minute candles", ident["symbol"], sid, len(candles))


class Ingest:
    """Owns the single upstream connection (plan §5.2 steps 1-5)."""

    def __init__(self, redis):
        self.redis = redis
        self.instruments: dict[str, str] = {}  # security id -> exchange segment
        self.builders: dict[str, CandleBuilder] = {}
        self.seq: dict[str, int] = defaultdict(int)
        self.ws = None

    async def add(self, sid: str, segment: str) -> None:
        if sid in self.instruments:
            return
        self.instruments[sid] = segment
        m1 = await load_m1(self.redis, sid)
        this_minute = int(time.time()) // 60 * 60
        # Resume the in-progress minute from seeded history so it isn't restarted.
        self.builders[sid] = CandleBuilder(current=m1[-1] if m1 and m1[-1][0] == this_minute else None)
        if self.ws is not None:
            try:
                for frame in subscribe_frames([(segment, sid)]):
                    await self.ws.send(json.dumps(frame))
            except websockets.ConnectionClosed:
                pass  # the reconnect re-subscribes every instrument
        logger.info("feed subscribed %s %s (%d instruments)", segment, sid, len(self.instruments))

    async def listen_for_subscriptions(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(rkey(SUBSCRIBE_CHANNEL))
        async for m in pubsub.listen():
            if m.get("type") == "message":
                req = json.loads(m["data"])
                await self.add(str(req["sid"]), str(req["segment"]))

    async def on_tick(self, tick: dict, t_recv: float) -> None:
        if tick["type"] == "disconnect":
            if tick["reason"] in FATAL_DISCONNECT:
                raise FatalFeedError(f"{FATAL_DISCONNECT[tick['reason']]} ({tick['reason']})")
            raise ConnectionError(f"feed disconnect code {tick['reason']}")
        if tick["type"] not in ("quote", "ticker"):
            return
        sid = tick["security_id"]
        builder = self.builders.get(sid)
        if builder is None:
            return
        self.seq[sid] += 1
        async with self.redis.pipeline(transaction=False) as pipe:
            # The last price is always valid (an illiquid stock's last trade may be minutes old)...
            pipe.hset(rkey(f"quote:{sid}"), mapping={"price": tick["ltp"], "ts": tick["ltt"], "seq": self.seq[sid]})
            # ...but only a fresh trade belongs in a candle; an old one would overwrite history.
            if tick["ltt"] >= t_recv - STALE_TICK_SECONDS:
                builder.update(tick["ltt"], tick["ltp"], tick.get("volume"))
                m1 = builder.current
                pipe.hset(_m1_key(sid), str(m1[0]), json.dumps(m1))
                pipe.publish(rkey(f"tick:{sid}"), json.dumps({
                    "sid": sid, "seq": self.seq[sid], "m1": m1, "price": tick["ltp"], "ts": tick["ltt"], "t_recv": t_recv,
                }))
            await pipe.execute()

    async def run(self) -> None:
        for sid, segment in (await self.redis.hgetall(rkey(INSTRUMENTS))).items():
            await self.add(sid, segment)
        listener = asyncio.create_task(self.listen_for_subscriptions())
        backoff = 1.0
        try:
            while True:
                url = feed_url(os.getenv("DHAN_ACCESS_TOKEN", "").strip(), os.getenv("DHAN_CLIENT_ID", "").strip())
                try:
                    async with websockets.connect(url, max_size=2**20) as ws:
                        self.ws = ws
                        if self.instruments:
                            for frame in subscribe_frames([(seg, sid) for sid, seg in self.instruments.items()]):
                                await ws.send(json.dumps(frame))
                        logger.info("feed connected (%d instruments)", len(self.instruments))
                        backoff = 1.0
                        seen_written = 0.0
                        async for message in ws:
                            t_recv = time.time()
                            if t_recv - seen_written >= 5:
                                await self.redis.set(rkey(FEED_SEEN), t_recv)
                                seen_written = t_recv
                            if isinstance(message, bytes):
                                for packet in iter_packets(message):
                                    tick = parse_packet(packet)
                                    if tick:
                                        await self.on_tick(tick, t_recv)
                except FatalFeedError as exc:
                    # Charts keep serving cached candles; re-read .env so a rotated token works without a restart.
                    logger.error("Dhan refused the feed: %s. Update DHAN_ACCESS_TOKEN; retrying in 60s.", exc)
                    await asyncio.sleep(60)
                    load_dotenv(override=True)
                except (OSError, websockets.ConnectionClosed, ConnectionError) as exc:
                    delay = backoff + random.random()
                    logger.warning("feed dropped (%s); reconnecting in %.1fs", exc, delay)
                    await asyncio.sleep(delay)
                    backoff = min(backoff * 2, 30.0)
                finally:
                    self.ws = None
        finally:
            listener.cancel()


class Gateway:
    """Browser sockets: ticket auth, snapshot on subscribe, then deltas (plan §5.4)."""

    def __init__(self, redis):
        self.redis = redis
        self.watchers: dict[tuple[str, int], dict] = defaultdict(dict)  # (sid, minutes) -> {socket: client key}
        self.recent: dict[str, dict[int, list]] = {}  # sid -> recent 1m candles, to roll up the current bar

    async def handler(self, ws) -> None:
        ticket = parse_qs(urlsplit(ws.request.path).query).get("ticket", [""])[0]
        if not ticket or not await self.redis.getdel(rkey(f"ticket:{ticket}")):
            await ws.close(4401, "Unauthorized")
            return
        watching: set[tuple[str, int]] = set()
        try:
            async for raw in ws:
                try:
                    req = json.loads(raw)
                except ValueError:
                    continue
                op = req.get("op")
                if op == "sub":
                    await self.subscribe(ws, req, watching)
                elif op == "unsub":
                    key = str(req.get("key", ""))
                    for slot in [s for s in watching if self.watchers[s].get(ws) == key]:
                        self.watchers[slot].pop(ws, None)
                        watching.discard(slot)
                elif op == "ping":
                    await ws.send(json.dumps({"op": "pong", "t": req.get("t")}))
        except websockets.ConnectionClosed:
            pass
        finally:
            for slot in watching:
                self.watchers[slot].pop(ws, None)

    async def subscribe(self, ws, req: dict, watching: set) -> None:
        key = str(req.get("key") or "")
        minutes = TIMEFRAMES.get(str(req.get("tf")))
        if not key or minutes is None:
            await ws.send(json.dumps({"op": "error", "key": key, "detail": "Unsupported timeframe."}))
            return
        try:
            ident = await dm._resolve_chart_identity(
                str(req.get("symbol", "")), req.get("securityId"), req.get("exchangeSegment"), req.get("instrument")
            )
            await ensure_seeded(self.redis, ident)
        except HTTPException as exc:
            logger.warning("subscribe %s failed: %s", req.get("symbol"), exc.detail)
            await ws.send(json.dumps({"op": "error", "key": key, "detail": "Chart data is unavailable for this symbol right now."}))
            return

        sid = str(ident["securityId"])
        await request_feed(self.redis, ident)

        m1 = await load_m1(self.redis, sid)
        if m1:
            self.recent[sid] = {c[0]: c for c in m1 if c[0] >= m1[-1][0] - 7200}
        await ws.send(json.dumps({
            "op": "snapshot", "key": key, "symbol": ident["symbol"], "tf": str(req.get("tf")),
            "candles": aggregate(m1, minutes)[-MAX_SNAPSHOT:],
            "last": await feed_quote(self.redis, ident),
            "market": await market_state(),
        }))
        # Register after the snapshot so no delta can arrive before it; the next tick carries the full bar.
        self.watchers[(sid, minutes)][ws] = key
        watching.add((sid, minutes))

    async def fanout(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.psubscribe(rkey("tick:*"))
        async for m in pubsub.listen():
            if m.get("type") != "pmessage":
                continue
            tick = json.loads(m["data"])
            sid, m1 = tick["sid"], tick["m1"]
            recent = self.recent.setdefault(sid, {})
            recent[m1[0]] = m1
            if len(recent) > 300:
                for t in [t for t in recent if t < m1[0] - 7200]:
                    del recent[t]
            for (wsid, minutes), clients in list(self.watchers.items()):
                if wsid != sid or not clients:
                    continue
                if minutes == 1:
                    candle = m1
                else:
                    start = bucket_start(m1[0], minutes)
                    candle = aggregate(sorted(c for t, c in recent.items() if start <= t < start + minutes * 60), minutes)[0]
                by_key: dict[str, list] = defaultdict(list)
                for client, key in clients.items():
                    by_key[key].append(client)
                for key, conns in by_key.items():
                    websockets.broadcast(conns, json.dumps({
                        "op": "delta", "key": key, "seq": tick["seq"], "candle": candle,
                        "last": {"price": tick["price"], "ts": tick["ts"]}, "t_recv": tick["t_recv"],
                    }))


def _health_check(connection, request):
    """Plain HTTP requests (host health checks) get 200 instead of a failed handshake."""
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return connection.respond(200, "ok\n")
    return None


async def main() -> None:
    redis = get_redis_client()
    if redis is None:
        raise SystemExit("REDIS_URL is not set")
    ingest, gateway = Ingest(redis), Gateway(redis)
    host, port = os.getenv("MARKET_HOST", "127.0.0.1"), int(os.getenv("MARKET_PORT", "8001"))
    async with websockets.serve(gateway.handler, host, port, process_request=_health_check):
        logger.info("market gateway listening on ws://%s:%d", host, port)
        await asyncio.gather(ingest.run(), gateway.fanout())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(main())
