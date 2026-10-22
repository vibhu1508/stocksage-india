"""Dhan feed parsing and candle building. Run: python -m tests.test_market_feed (from backend/), or pytest."""

import struct

from datetime import datetime, timezone

from market.candles import IST, CandleBuilder, aggregate, bucket_start
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


def _ist(hh, mm):
    return int(datetime(2026, 10, 22, hh, mm, tzinfo=IST).timestamp())


def test_buckets_anchor_at_0915_like_dhan():
    # Dhan's 60m bars open 09:15, 10:15...; 25m bars 09:15, 09:40, 10:05... (checked against REST 22 Oct)
    assert bucket_start(_ist(10, 14) + 59, 60) == _ist(9, 15)
    assert bucket_start(_ist(10, 15), 60) == _ist(10, 15)
    assert bucket_start(_ist(10, 4), 25) == _ist(9, 40)
    assert bucket_start(_ist(13, 37), 5) == _ist(13, 35)
    assert bucket_start(_ist(13, 37) + 42, 1) == _ist(13, 37)


def test_aggregate_rolls_up_ohlcv_without_the_auction_minute():
    auction = [_ist(9, 15), 20, 21, 19, 20, 999]  # pre-open auction bar: Dhan's 5m+ bars exclude it
    m1 = [auction, [_ist(9, 16), 11, 15, 10, 14, 50], [_ist(9, 17), 14, 16, 9, 12, 25], [_ist(9, 20), 14, 14, 8, 9, 7]]
    assert aggregate(m1, 5) == [[_ist(9, 15), 11, 16, 9, 12, 75], [_ist(9, 20), 14, 14, 8, 9, 7]]
    assert aggregate(m1, 1) == m1  # 1m keeps it, like Dhan's 1m history


def test_builder_resumes_seeded_minute():
    b = CandleBuilder(current=[600, 100.0, 105.0, 99.0, 104.0, 900])
    b.update(630, 106.0, 50_000)  # first tick only sets the volume baseline
    b.update(640, 98.0, 50_040)
    assert b.current == [600, 100.0, 106.0, 98.0, 98.0, 940]


def test_quote_message_day_change():
    import os
    os.environ.setdefault("SECRET_KEY", "test-only-secret")
    from market.service import quote_message

    # Redis hands back strings; prev close 1209 is NSE's official close for RELIANCE on 21 Oct.
    msg = quote_message("Q:RELIANCE", {"price": "1189.4", "ts": "1792659000", "prev_close": "1209", "high": "1208"})
    assert (msg["change"], msg["pct"], msg["high"]) == (-19.6, -1.62, 1208.0)
    # Before the previous close is fetched, the price still streams without a made-up change.
    assert quote_message("Q:X", {"price": "10", "ts": "1"})["change"] is None


def test_prev_close_is_the_close_before_the_session():
    import os
    os.environ.setdefault("SECRET_KEY", "test-only-secret")
    from market.service import prev_close_from_daily, session_date

    # NIFTY daily candles (IST midnight) as Dhan returned them on 22 Oct; 20 Oct was a holiday.
    day = lambda d: int(datetime(2026, 10, d, tzinfo=IST).timestamp())
    daily = {"timestamp": [day(16), day(19), day(21)], "close": [23146.15, 22888.95, 22811.35]}
    assert prev_close_from_daily(daily, "2026-10-22") == 22811.35
    # Once Dhan adds the session's own candle it must be skipped, or the change reads 0%.
    with_today = {"timestamp": daily["timestamp"] + [day(22)], "close": daily["close"] + [22687.65]}
    assert prev_close_from_daily(with_today, "2026-10-22") == 22811.35
    assert prev_close_from_daily({"timestamp": [day(22)], "close": [1.0]}, "2026-10-22") is None
    assert prev_close_from_daily({}, "2026-10-22") is None
    # The session is the IST date of the last trade: 00:30 IST is the next day, 23:59 IST is not.
    assert session_date(datetime(2026, 10, 22, 19, 0, tzinfo=timezone.utc).timestamp()) == "2026-10-23"
    assert session_date(datetime(2026, 10, 22, 18, 29, tzinfo=timezone.utc).timestamp()) == "2026-10-22"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
