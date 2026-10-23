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
from services import daily_store  # noqa: E402
from services.redis_store import _key as rkey, get_redis_client  # noqa: E402
from utils.market_utils import get_latest_market_date, is_market_holiday  # noqa: E402

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
QUOTE_MIN_GAP_SECONDS = 0.25
DAILY_INSTRUMENT = {"IDX_I": "INDEX", "NSE_EQ": "EQUITY", "BSE_EQ": "EQUITY"}  # Dhan daily-candle types


class FatalFeedError(RuntimeError):
    """Dhan refused the feed for a reason a retry with the same token cannot fix."""


def instrument_key(segment: str, security_id) -> str:
    """Redis and in-memory key for one instrument. Security IDs repeat across segments (NIFTY 50
    and ABB are both 13; NIFTY BANK and ADANIENT both 25), so the segment is part of the key."""
    return f"{segment}:{security_id}"


def _ident_key(ident: dict) -> str:
    return instrument_key(ident["exchangeSegment"], ident["securityId"])


def _m1_key(ikey: str) -> str:
    return rkey(f"m1:{ikey}")


async def load_m1(redis, ikey: str) -> list[list]:
    raw = await redis.hgetall(_m1_key(ikey))
    return sorted((json.loads(v) for v in raw.values()), key=lambda c: c[0])


async def market_state() -> str:
    now = datetime.now(IST)
    if await asyncio.to_thread(is_market_holiday, now.date()):
        return "closed"
    minute = now.hour * 60 + now.minute
    return "open" if 9 * 60 + 15 <= minute < 15 * 60 + 30 else "closed"


async def request_feed(redis, ident: dict) -> None:
    """Ask ingest to stream this instrument (idempotent). Used by the gateway and by REST
    readers such as the portfolio, which then read `quote:{segment:id}`."""
    ikey = _ident_key(ident)
    await redis.hset(rkey(INSTRUMENTS), ikey, ident["exchangeSegment"])
    await redis.publish(rkey(SUBSCRIBE_CHANNEL), json.dumps({"key": ikey}))


async def feed_alive(redis) -> bool:
    """True when ingest received a packet in the last FEED_ALIVE_SECONDS (any symbol)."""
    seen = await redis.get(rkey(FEED_SEEN))
    return bool(seen) and float(seen) >= time.time() - FEED_ALIVE_SECONDS


async def feed_quote(redis, ident: dict) -> Optional[dict]:
    """Latest feed price for an instrument as {price, ts}, or None if the feed hasn't seen one yet."""
    quote = await redis.hgetall(rkey(f"quote:{_ident_key(ident)}"))
    if not (quote.get("ts") and float(quote.get("price") or 0) > 0):
        return None
    return {"price": float(quote["price"]), "ts": int(quote["ts"])}


def session_date(ltt: float) -> str:
    """The trading session a quote belongs to: the IST date of its last trade, so nights,
    weekends and holidays still count as the last session."""
    return datetime.fromtimestamp(ltt, IST).date().isoformat()


def prev_close_from_daily(data: dict, session: str) -> Optional[float]:
    """Close of the last daily candle before `session`. Dhan's quote API and feed can't be
    used after hours: both then report the session's own close, giving 0% for everything."""
    before = [(t, c) for t, c in zip(data.get("timestamp") or [], data.get("close") or []) if c and session_date(t) < session]
    return float(max(before)[1]) if before else None


def quote_message(key: str, q: dict) -> dict:
    """Wire shape of a live quote: last price with day change against the previous close."""
    price, prev = float(q["price"]), q.get("prev_close")
    prev = float(prev) if prev not in (None, "") else None
    change = round(price - prev, 2) if prev else None
    msg = {
        "op": "quote", "key": key, "price": price, "ts": int(float(q["ts"])), "prev_close": prev,
        "change": change, "pct": round(change / prev * 100, 2) if prev else None,
    }
    for field in ("open", "high", "low", "volume"):
        if q.get(field) not in (None, ""):
            msg[field] = float(q[field])
    return msg


def _history_candles(data: dict) -> list[list]:
    """Dhan intraday arrays -> [[t, o, h, l, c, v], ...], keeping volume."""
    cols = [data.get(k) or [] for k in ("timestamp", "open", "high", "low", "close", "volume")]
    return [[int(t), float(o), float(h), float(l), float(c), int(v or 0)] for t, o, h, l, c, v in zip(*cols)]


_seed_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def ensure_seeded(redis, ident: dict) -> None:
    """Load about a week of 1-minute history once per symbol per day (plan §5.2 step 7)."""
    sid = str(ident["securityId"])
    ikey = _ident_key(ident)
    today = datetime.now(IST).date().isoformat()
    async with _seed_locks[ikey]:
        if await redis.get(rkey(f"seeded:{ikey}")) == today:
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
            pipe.delete(_m1_key(ikey))
            if candles:
                pipe.hset(_m1_key(ikey), mapping={str(c[0]): json.dumps(c) for c in candles})
                pipe.expire(_m1_key(ikey), CANDLE_TTL)
            pipe.set(rkey(f"seeded:{ikey}"), today, ex=86400)
            await pipe.execute()
        logger.info("seeded %s (%s): %d one-minute candles", ident["symbol"], ikey, len(candles))


class Ingest:
    """Owns the single upstream connection (plan §5.2 steps 1-5)."""

    def __init__(self, redis):
        self.redis = redis
        self.instruments: dict[str, tuple[str, str]] = {}  # "segment:id" -> (segment, security id)
        self.builders: dict[str, CandleBuilder] = {}
        self.seq: dict[str, int] = defaultdict(int)
        self.prev_close: dict[str, float] = {}  # for day change; Dhan's quote packets don't carry it
        self.prev_close_session: dict[str, str] = {}  # session date each prev close belongs to
        self.prev_close_pending: dict[str, str] = {}  # instrument key -> session awaiting its prev close
        self.ws = None

    async def add(self, ikey: str) -> None:
        if ikey in self.instruments:
            return
        segment, sid = ikey.split(":", 1)
        self.instruments[ikey] = (segment, sid)
        m1 = await load_m1(self.redis, ikey)
        this_minute = int(time.time()) // 60 * 60
        # Resume the in-progress minute from seeded history so it isn't restarted.
        self.builders[ikey] = CandleBuilder(current=m1[-1] if m1 and m1[-1][0] == this_minute else None)
        stored = await self.redis.hmget(rkey(f"quote:{ikey}"), "prev_close", "prev_close_session", "ts", "price")
        last_trade = float(stored[2] or 0)
        if stored[2] and last_trade <= 0:  # written by a pre-open placeholder before those were dropped
            await self.redis.hdel(rkey(f"quote:{ikey}"), "ts")
        if stored[0] and stored[1]:
            self.prev_close[ikey], self.prev_close_session[ikey] = float(stored[0]), stored[1]
        else:  # untagged values came from the quote API and may be the session's own close
            await self.redis.hdel(rkey(f"quote:{ikey}"), "prev_close", "prev_close_date")
            if stored[3]:  # a known last price: work out its previous close now, not on the next tick
                self.prev_close_pending[ikey] = session_date(last_trade) if last_trade > 0 else \
                    get_latest_market_date(datetime.now(IST)).isoformat()
        if self.ws is not None:
            try:
                for frame in subscribe_frames([(segment, sid)]):
                    await self.ws.send(json.dumps(frame))
            except websockets.ConnectionClosed:
                pass  # the reconnect re-subscribes every instrument
        logger.info("feed subscribed %s %s (%d instruments)", segment, ikey, len(self.instruments))

    async def listen_for_subscriptions(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(rkey(SUBSCRIBE_CHANNEL))
        async for m in pubsub.listen():
            if m.get("type") == "message":
                req = json.loads(m["data"])
                await self.add(str(req["key"]))

    async def prev_close_loop(self) -> None:
        """Previous close for each instrument's session from the daily store (services/daily_store.py),
        which refreshes from the providers at most once per session per instrument."""
        retry_at: dict[str, float] = {}  # instruments whose daily candles are unavailable everywhere
        while True:
            await asyncio.sleep(2)
            for ikey, session in list(self.prev_close_pending.items()):
                if retry_at.get(ikey, 0) > time.time():
                    continue
                segment, sid = self.instruments[ikey]
                if segment not in DAILY_INSTRUMENT:
                    # shortcut: no day change for F&O/currency/commodity (daily candles need the contract type); add when those stream live
                    self.prev_close_session[ikey] = self.prev_close_pending.pop(ikey)  # don't re-queue on every tick
                    continue
                try:
                    rows = await daily_store.daily_rows(
                        {"exchangeSegment": segment, "securityId": sid, "instrument": DAILY_INSTRUMENT[segment]})
                    await asyncio.sleep(1)  # a refresh may have called the provider: keep a gentle pace
                except HTTPException as exc:
                    logger.warning("previous close unavailable for %s: %s; retrying in 15 min", ikey, exc.detail)
                    retry_at[ikey] = time.time() + 900
                    continue  # the instrument stays pending
                if self.prev_close_pending.get(ikey) != session:
                    continue  # a newer session began while fetching
                del self.prev_close_pending[ikey]
                self.prev_close_session[ikey] = session
                close = prev_close_from_daily({"timestamp": [r[0] for r in rows], "close": [r[4] for r in rows]}, session)
                if close is None:  # e.g. listed this session
                    continue
                self.prev_close[ikey] = close
                await self.redis.hset(rkey(f"quote:{ikey}"), mapping={"prev_close": close, "prev_close_session": session})

    async def on_tick(self, tick: dict, t_recv: float) -> None:
        if tick["type"] == "disconnect":
            if tick["reason"] in FATAL_DISCONNECT:
                raise FatalFeedError(f"{FATAL_DISCONNECT[tick['reason']]} ({tick['reason']})")
            raise ConnectionError(f"feed disconnect code {tick['reason']}")
        if tick["type"] not in ("quote", "ticker"):
            return
        # Placeholders, not trades: price 0 for a stock that hasn't traded, or (before the open) a real
        # last price with last-trade time 0, which would stamp the quote 1970 and break the session.
        if tick["ltp"] <= 0 or tick["ltt"] <= 0:
            return
        ikey = instrument_key(tick["segment"], tick["security_id"])
        builder = self.builders.get(ikey)
        if builder is None:
            return
        self.seq[ikey] += 1
        session = session_date(tick["ltt"])
        new_session = self.prev_close_session.get(ikey) != session and self.prev_close_pending.get(ikey) != session
        if new_session:  # yesterday's prev close would give a wrong change until the new one arrives
            self.prev_close.pop(ikey, None)
            self.prev_close_pending[ikey] = session
        quote = {"price": tick["ltp"], "ts": tick["ltt"], "seq": self.seq[ikey]}
        if tick["type"] == "quote":
            quote.update({k: tick[k] for k in ("open", "high", "low", "volume")})
        m1 = None
        async with self.redis.pipeline(transaction=False) as pipe:
            # The last price is always valid (an illiquid stock's last trade may be minutes old)...
            if new_session:
                pipe.hdel(rkey(f"quote:{ikey}"), "prev_close")
            pipe.hset(rkey(f"quote:{ikey}"), mapping=quote)
            # ...but only a fresh trade belongs in a candle; an old one would overwrite history.
            if tick["ltt"] >= t_recv - STALE_TICK_SECONDS:
                builder.update(tick["ltt"], tick["ltp"], tick.get("volume"))
                m1 = builder.current
                pipe.hset(_m1_key(ikey), str(m1[0]), json.dumps(m1))
            pipe.publish(rkey(f"tick:{ikey}"), json.dumps({
                **quote, "ikey": ikey, "m1": m1, "prev_close": self.prev_close.get(ikey), "t_recv": t_recv,
            }))
            await pipe.execute()

    async def add_saved(self) -> None:
        """Re-subscribe everything requested before a restart."""
        for field, segment in (await self.redis.hgetall(rkey(INSTRUMENTS))).items():
            # Entries written before keys carried the segment are a bare id with the segment as value.
            await self.add(field if ":" in field else instrument_key(segment, field))

    async def run(self) -> None:
        await self.add_saved()
        listener = asyncio.create_task(self.listen_for_subscriptions())
        prev_closes = asyncio.create_task(self.prev_close_loop())
        backoff = 1.0
        try:
            while True:
                url = feed_url(os.getenv("DHAN_ACCESS_TOKEN", "").strip(), os.getenv("DHAN_CLIENT_ID", "").strip())
                try:
                    async with websockets.connect(url, max_size=2**20) as ws:
                        self.ws = ws
                        if self.instruments:
                            for frame in subscribe_frames(list(self.instruments.values())):
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
            prev_closes.cancel()


class Gateway:
    """Browser sockets: ticket auth, snapshot on subscribe, then deltas (plan §5.4)."""

    def __init__(self, redis):
        self.redis = redis
        # (instrument key, minutes) -> {socket: client key}; minutes 0 is a live-quote watcher (price + day change)
        self.watchers: dict[tuple[str, int], dict] = defaultdict(dict)
        self.recent: dict[str, dict[int, list]] = {}  # ikey -> recent 1m candles, to roll up the current bar
        self.quote_sent: dict[str, float] = {}  # ikey -> last live-quote broadcast time

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
                elif op == "quote":
                    await self.subscribe_quote(ws, req, watching)
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

        ikey = _ident_key(ident)
        await request_feed(self.redis, ident)

        m1 = await load_m1(self.redis, ikey)
        if m1:
            self.recent[ikey] = {c[0]: c for c in m1 if c[0] >= m1[-1][0] - 7200}
        await ws.send(json.dumps({
            "op": "snapshot", "key": key, "symbol": ident["symbol"], "tf": str(req.get("tf")),
            "candles": aggregate(m1, minutes)[-MAX_SNAPSHOT:],
            "last": await feed_quote(self.redis, ident),
            "market": await market_state(),
        }))
        # Register after the snapshot so no delta can arrive before it; the next tick carries the full bar.
        self.watchers[(ikey, minutes)][ws] = key
        watching.add((ikey, minutes))

    async def subscribe_quote(self, ws, req: dict, watching: set) -> None:
        """Live price and day change for one instrument (dashboard indices, stock header, movers)."""
        key = str(req.get("key") or "")
        try:
            ident = await dm._resolve_chart_identity(
                str(req.get("symbol", "")), req.get("securityId"), req.get("exchangeSegment"), req.get("instrument")
            )
        except HTTPException:
            await ws.send(json.dumps({"op": "error", "key": key, "detail": "Live price is unavailable for this symbol."}))
            return
        ikey = _ident_key(ident)
        await request_feed(self.redis, ident)
        current = await self.redis.hgetall(rkey(f"quote:{ikey}"))
        if current.get("ts") and float(current.get("price") or 0) > 0:
            await ws.send(json.dumps(quote_message(key, current)))
        self.watchers[(ikey, 0)][ws] = key
        watching.add((ikey, 0))

    async def fanout(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.psubscribe(rkey("tick:*"))
        async for m in pubsub.listen():
            if m.get("type") != "pmessage":
                continue
            tick = json.loads(m["data"])
            ikey, m1 = tick["ikey"], tick["m1"]  # m1 is None for a quote too old to belong in a candle
            if m1:
                recent = self.recent.setdefault(ikey, {})
                recent[m1[0]] = m1
                if len(recent) > 300:
                    for t in [t for t in recent if t < m1[0] - 7200]:
                        del recent[t]
            for (wkey, minutes), clients in list(self.watchers.items()):
                if wkey != ikey or not clients or (minutes and not m1):
                    continue
                by_key: dict[str, list] = defaultdict(list)
                for client, key in clients.items():
                    by_key[key].append(client)
                if minutes == 0:
                    # Indices tick ~10/s; 4/s is still live to the eye and keeps price flashes readable.
                    # shortcut: drops in-between ticks without a trailing flush; fine while the next tick
                    # follows within a second, revisit if a slow symbol shows a stale last value.
                    if time.time() - self.quote_sent.get(ikey, 0.0) < QUOTE_MIN_GAP_SECONDS:
                        continue
                    self.quote_sent[ikey] = time.time()
                    for key, conns in by_key.items():
                        websockets.broadcast(conns, json.dumps(quote_message(key, tick)))
                    continue
                if minutes == 1:
                    candle = m1
                else:
                    start = bucket_start(m1[0], minutes)
                    candle = aggregate(sorted(c for t, c in recent.items() if start <= t < start + minutes * 60), minutes)[0]
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
