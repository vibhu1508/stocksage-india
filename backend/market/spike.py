"""
Phase 1 market-data spike (plan §16 step 4): the go/no-go for the real-time path.

One Dhan feed connection -> 1m candles -> Redis (quote hash + pub/sub) -> gateway socket
-> a probe client, with a timestamp at every hop (plan §5.5). Not wired into the API.

Run from backend/ with Redis at REDIS_URL and a valid Dhan token in .env:
    python -m market.spike --symbols RELIANCE,TCS,HDFCBANK --seconds 120

What it measures: Dhan -> our ingest (from the trade time) and every hop on our side.
What it cannot: the user's last mile; the probe runs on this machine.
"""

import argparse
import asyncio
import json
import logging
import os
import random
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone

import websockets
from dotenv import load_dotenv

load_dotenv()

from market.candles import CandleBuilder  # noqa: E402
from market.feed import FATAL_DISCONNECT, feed_url, iter_packets, parse_packet, subscribe_frames  # noqa: E402
from routers import dhan_market as dm  # noqa: E402
from services.redis_store import _key as rkey, get_redis_client  # noqa: E402

logger = logging.getLogger("market.spike")
QUOTE_TTL = 86400


class FatalFeedError(RuntimeError):
    """The feed refused us for a reason a retry cannot fix (expired token, bad client ID...)."""


async def ingest(instruments: list[tuple[str, str]], names: dict, stats: dict) -> None:
    """Own the single upstream connection; reconnect with backoff and jitter (plan §5.8)."""
    redis = get_redis_client()
    builders = defaultdict(CandleBuilder)
    seq: dict[str, int] = defaultdict(int)
    # DHAN_FEED_URL points at a local fake feed for offline runs (plan §4.4).
    url = os.getenv("DHAN_FEED_URL") or feed_url(
        os.environ["DHAN_ACCESS_TOKEN"].strip(), os.environ["DHAN_CLIENT_ID"].strip()
    )
    backoff = 1.0

    while True:
        try:
            async with websockets.connect(url, max_size=2**20) as ws:
                for frame in subscribe_frames(instruments):
                    await ws.send(json.dumps(frame))
                logger.info("feed connected, subscribed %d instruments", len(instruments))
                backoff = 1.0
                async for message in ws:
                    t_recv = time.time()
                    if isinstance(message, str):
                        continue
                    for packet in iter_packets(message):
                        tick = parse_packet(packet)
                        if not tick:
                            continue
                        if tick["type"] == "disconnect":
                            reason = tick["reason"]
                            if reason in FATAL_DISCONNECT:
                                raise FatalFeedError(f"{FATAL_DISCONNECT[reason]} ({reason})")
                            raise ConnectionError(f"feed disconnect code {reason}")
                        if tick["type"] != "quote":
                            continue
                        sid = tick["security_id"]
                        seq[sid] += 1
                        closed = builders[sid].update(tick["ltt"], tick["ltp"], tick["volume"])
                        if closed:
                            stats["candles_closed"] += 1
                            opened = datetime.fromtimestamp(closed[0], timezone.utc).astimezone(dm.IST)
                            logger.info("candle %s %s O=%s H=%s L=%s C=%s V=%s", names.get(sid, sid),
                                        f"{opened:%H:%M}", *closed[1:])
                        msg = {
                            "op": "delta", "symbol": names.get(sid, sid), "sid": sid, "tf": "1m",
                            "seq": seq[sid], "candle": builders[sid].current, "last": tick["ltp"],
                            "ltt": tick["ltt"], "t_recv": t_recv, "t_pub": time.time(),
                        }
                        async with redis.pipeline(transaction=False) as pipe:
                            pipe.hset(rkey(f"quote:{sid}"), mapping={
                                "price": tick["ltp"], "volume": tick["volume"], "ltt": tick["ltt"],
                                "seq": seq[sid], "t_recv": t_recv,
                            })
                            pipe.expire(rkey(f"quote:{sid}"), QUOTE_TTL)
                            pipe.publish(rkey(f"tick:{sid}"), json.dumps(msg))
                            await pipe.execute()
                        stats["ticks"] += 1
        except FatalFeedError:
            raise
        except (OSError, websockets.ConnectionClosed, ConnectionError) as exc:
            stats["reconnects"] += 1
            delay = backoff + random.random()
            logger.warning("feed dropped (%s); reconnecting in %.1fs", exc, delay)
            await asyncio.sleep(delay)
            backoff = min(backoff * 2, 30.0)


async def gateway(port: int) -> None:
    """Fan out per symbol: one Redis subscription, local broadcast to every socket on it."""
    redis = get_redis_client()
    clients: dict[str, set] = defaultdict(set)

    async def handler(ws):
        # shortcut: no auth, bound to 127.0.0.1 for the spike; the real gateway takes a ticket (plan §5.4).
        watching: set[str] = set()
        try:
            async for raw in ws:
                req = json.loads(raw)
                if req.get("op") == "sub":
                    sid = str(req["sid"])
                    clients[sid].add(ws)
                    watching.add(sid)
                    last = await redis.hgetall(rkey(f"quote:{sid}"))
                    await ws.send(json.dumps({"op": "snapshot", "sid": sid, "last": last}))
        finally:
            for sid in watching:
                clients[sid].discard(ws)

    # shortcut: pattern subscription to all ticks; per-symbol subscribe once >1 gateway instance.
    pubsub = redis.pubsub()
    await pubsub.psubscribe(rkey("tick:*"))
    async with websockets.serve(handler, "127.0.0.1", port):
        async for m in pubsub.listen():
            if m.get("type") != "pmessage":
                continue
            msg = json.loads(m["data"])
            msg["t_send"] = time.time()
            websockets.broadcast(clients.get(msg["sid"], ()), json.dumps(msg))


async def probe(port: int, sids: list[str], stats: dict) -> None:
    """A client that records each hop's latency and any sequence gaps."""
    await asyncio.sleep(0.5)
    async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
        for sid in sids:
            await ws.send(json.dumps({"op": "sub", "sid": sid}))
        last_seq: dict[str, int] = {}
        async for raw in ws:
            t_client = time.time()
            m = json.loads(raw)
            if m["op"] != "delta":
                continue
            prev = last_seq.get(m["sid"])
            if prev is not None and m["seq"] != prev + 1:
                stats["seq_gaps"] += 1
            last_seq[m["sid"]] = m["seq"]
            stats["lat"]["recv_to_pub"].append((m["t_pub"] - m["t_recv"]) * 1000)
            stats["lat"]["pub_to_send"].append((m["t_send"] - m["t_pub"]) * 1000)
            stats["lat"]["send_to_client"].append((t_client - m["t_send"]) * 1000)
            stats["lat"]["recv_to_client"].append((t_client - m["t_recv"]) * 1000)
            # Trade time has 1 s resolution, so this overstates Dhan's lag by ~0.5 s on average.
            stats["lat"]["ltt_to_recv"].append((m["t_recv"] - m["ltt"]) * 1000)


def report(stats: dict, elapsed: float) -> str:
    def pct(values, q):
        return statistics.quantiles(values, n=100)[q - 1] if len(values) >= 2 else (values[0] if values else 0.0)

    lines = [f"{elapsed:.0f}s  ticks={stats['ticks']} ({stats['ticks'] / max(elapsed, 1):.1f}/s)  "
             f"candles_closed={stats['candles_closed']}  seq_gaps={stats['seq_gaps']}  reconnects={stats['reconnects']}"]
    for stage, values in stats["lat"].items():
        if values:
            lines.append(f"  {stage:<15} p50={pct(values, 50):9.2f} ms  p95={pct(values, 95):9.2f} ms  "
                         f"p99={pct(values, 99):9.2f} ms  n={len(values)}")
    return "\n".join(lines)


async def main(symbols: list[str], seconds: int, port: int) -> None:
    if get_redis_client() is None:
        raise SystemExit("REDIS_URL is not set")
    instruments, names = [], {}
    for symbol in symbols:
        ident = await dm._resolve_chart_identity(symbol, None, None, None)
        instruments.append((ident["exchangeSegment"], str(ident["securityId"])))
        names[str(ident["securityId"])] = symbol

    stats = {"ticks": 0, "candles_closed": 0, "seq_gaps": 0, "reconnects": 0, "lat": defaultdict(list)}
    tasks = [
        asyncio.create_task(ingest(instruments, names, stats)),
        asyncio.create_task(gateway(port)),
        asyncio.create_task(probe(port, list(names), stats)),
    ]
    started = time.time()
    next_report = started + 15
    try:
        while time.time() - started < seconds:
            done = [t for t in tasks if t.done()]
            if done:
                done[0].result()  # surface a crashed task (e.g. FatalFeedError) instead of hanging
            await asyncio.sleep(1)
            if time.time() >= next_report:
                print(report(stats, time.time() - started), flush=True)
                next_report += 15
    finally:
        for t in tasks:
            t.cancel()
        print("\nFINAL\n" + report(stats, time.time() - started), flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="RELIANCE,TCS,HDFCBANK,INFY,SBIN")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        asyncio.run(main([s.strip().upper() for s in args.symbols.split(",") if s.strip()], args.seconds, args.port))
    except FatalFeedError as exc:
        raise SystemExit(f"FAIL  Dhan closed the feed: {exc}")
