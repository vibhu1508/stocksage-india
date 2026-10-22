"""Dhan feed parsing and candle building. Run: python -m tests.test_market_feed (from backend/), or pytest."""

import struct

from market.candles import CandleBuilder
from market.feed import iter_packets, parse_packet, subscribe_frames


def _quote_packet(sid=2885, ltp=2911.25, ltt=1792660000, volume=120000):
    body = struct.pack("<fhifiiiffff", ltp, 10, ltt, 2905.5, volume, 1, 2, 2900.0, 0.0, 2920.0, 2890.0)
    return struct.pack("<BHBi", 4, 8 + len(body), 1, sid) + body


def test_parse_quote_packet():
    tick = parse_packet(_quote_packet())
    assert tick["type"] == "quote" and tick["segment"] == "NSE_EQ" and tick["security_id"] == "2885"
    assert tick["ltp"] == 2911.25 and tick["volume"] == 120000
    assert tick["ltt"] == 1792660000 - 19800  # Dhan sends IST-shifted epoch; we store true UTC
    assert (tick["open"], tick["high"], tick["low"]) == (2900.0, 2920.0, 2890.0)


def test_float32_prices_rounded_to_tick_precision():
    assert parse_packet(_quote_packet(ltp=2495.4))["ltp"] == 2495.4  # float32 gives 2495.39990234


def test_parse_disconnect_and_unknown():
    disconnect = struct.pack("<BHBi", 50, 10, 1, 2885) + struct.pack("<h", 807)
    assert parse_packet(disconnect) == {"segment": "NSE_EQ", "security_id": "2885", "type": "disconnect", "reason": 807}
    assert parse_packet(struct.pack("<BHBi", 7, 8, 1, 1)) is None  # market status: not used yet
    assert parse_packet(b"\x04\x00") is None  # truncated


def test_iter_packets_splits_concatenated_frames():
    frame = _quote_packet(sid=1) + _quote_packet(sid=2)
    assert [parse_packet(p)["security_id"] for p in iter_packets(frame)] == ["1", "2"]


def test_subscribe_frames_chunk_at_100():
    frames = subscribe_frames([("NSE_EQ", str(i)) for i in range(250)])
    assert [f["InstrumentCount"] for f in frames] == [100, 100, 50]
    assert frames[0]["RequestCode"] == 17 and frames[0]["InstrumentList"][0] == {"ExchangeSegment": "NSE_EQ", "SecurityId": "0"}


def test_candles_ohlcv_and_rollover():
    b = CandleBuilder()
    assert b.update(600, 100.0, 1000) is None            # opens 600; first tick sets the volume baseline
    assert b.update(615, 103.0, 1300) is None
    assert b.update(630, 99.0, 1350) is None
    assert b.update(659, 101.0, 1400) is None
    closed = b.update(660, 102.0, 1500)                   # next minute closes the first
    assert closed == [600, 100.0, 103.0, 99.0, 101.0, 400]
    assert b.current == [660, 102.0, 102.0, 102.0, 102.0, 100]
    assert b.update(640, 50.0, 1600) is None and b.current[3] == 102.0  # late tick ignored
    b.update(661, 103.0, 1200)                            # volume reset (e.g. new session) never goes negative
    assert b.current[5] >= 100


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
