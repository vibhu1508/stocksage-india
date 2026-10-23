"""Daily candle store. Run: python -m tests.test_daily_store (from backend/), or pytest."""

import asyncio
import os
import tempfile
from datetime import date
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-only-secret")
os.environ["REDIS_URL"] = ""

from fastapi import HTTPException  # noqa: E402

from services import daily_store as ds  # noqa: E402

ds.DB_PATH = Path(tempfile.mkdtemp()) / "daily.sqlite"
TCS = {"exchangeSegment": "NSE_EQ", "securityId": "11536", "instrument": "EQUITY"}


def test_day_stamp_matches_dhan_and_nse_rows():
    # Dhan's daily candle for 21 Oct 2026 carries 1792521000 (IST midnight).
    assert ds.day_stamp(date(2026, 10, 21)) == 1792521000
    nse = [{"mTIMESTAMP": "21-Oct-2026", "CH_SERIES": "EQ", "CH_OPENING_PRICE": 2520, "CH_TRADE_HIGH_PRICE": 2533,
            "CH_TRADE_LOW_PRICE": 2479, "CH_CLOSING_PRICE": 2529, "CH_TOT_TRADED_QTY": 1000},
           {"mTIMESTAMP": "21-Oct-2026", "CH_SERIES": "BL", "CH_OPENING_PRICE": 9, "CH_TRADE_HIGH_PRICE": 9,
            "CH_TRADE_LOW_PRICE": 9, "CH_CLOSING_PRICE": 9}]
    assert ds.nse_equity_rows(nse, "EQ") == [(1792521000, 2520, 2533, 2479, 2529, 1000)]  # block-deal row dropped
    idx = [{"EOD_TIMESTAMP": "21-OCT-2026", "EOD_OPEN_INDEX_VAL": 1, "EOD_HIGH_INDEX_VAL": 2, "EOD_LOW_INDEX_VAL": 0.5,
            "EOD_CLOSE_INDEX_VAL": 1.5}]
    assert ds.nse_index_rows(idx)[0][0] == 1792521000


def test_upsert_is_idempotent_and_reads_in_order():
    rows = [(1792521000, 1, 2, 0.5, 1.5, 10), (1792434600, 1, 2, 0.5, 1.4, 10)]
    ds.upsert("NSE_EQ", "1", rows, "dhan")
    ds.upsert("NSE_EQ", "1", rows, "dhan")
    assert [r[0] for r in ds.read("NSE_EQ", "1")] == [1792434600, 1792521000]


def test_split_detection():
    stored = [(1, 0, 0, 0, 1534.30, 0)]           # KIRLPNU's raw close the day before its 1:2 split
    assert ds.needs_refill(stored, [(1, 0, 0, 0, 767.15, 0)])       # Dhan's adjusted close for that day
    assert not ds.needs_refill(stored, [(1, 0, 0, 0, 1534.30, 0), (2, 0, 0, 0, 760, 0)])


def test_read_path_checks_once_per_session_and_survives_outages():
    calls = []
    replies = []

    async def fake_fetch(identity, start, end):
        calls.append(start)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply, "dhan"

    original, ds.fetch = ds.fetch, fake_fetch
    session = ds.get_latest_market_date(ds.datetime.now(ds.IST))
    today_row = (ds.day_stamp(session), 1, 2, 0.5, 2020, 5)
    try:
        # The provider doesn't have the latest session yet (it publishes the next morning).
        replies.append([(1792434600, 1, 2, 0.5, 2000, 5), (1792521000, 1, 2, 0.5, 2010, 5)])
        early = asyncio.run(ds.daily_rows(TCS))
        assert len(early) == 2 and calls == [ds.HISTORY_START]          # empty store: full history
        assert asyncio.run(ds.daily_rows(TCS)) == early and len(calls) == 1  # asked recently: no call
        ds.mark_checked("NSE_EQ", "11536", "")                           # ...as if 30 minutes passed
        with ds._connect() as conn:
            conn.execute("UPDATE checked SET at = 0")
        replies.append([(1792521000, 1, 2, 0.5, 2010, 5), today_row])
        first = asyncio.run(ds.daily_rows(TCS))
        assert len(first) == 3 and len(calls) == 2                        # the session's candle arrived
        assert asyncio.run(ds.daily_rows(TCS)) == first and len(calls) == 2  # complete: no more calls

        # Next session, the providers are down: the stored candles are served.
        with ds._connect() as conn:
            conn.execute("UPDATE checked SET session = '2000-01-01', at = 0")
        replies.append(HTTPException(status_code=502, detail="Daily candles unavailable"))
        assert asyncio.run(ds.daily_rows(TCS)) == first
        assert calls[-1] == ds.datetime.fromtimestamp(today_row[0], ds.IST).date() - ds.timedelta(days=10)  # 10-day overlap

        # A refetch that disagrees on a stored day means a split: the whole history is replaced.
        with ds._connect() as conn:
            conn.execute("UPDATE checked SET session = '2000-01-01', at = 0")
        replies.append([(1792521000, 1, 2, 0.5, 1005, 5)])
        replies.append([(1792434600, 0.5, 1, 0.25, 1000, 10), (1792521000, 0.5, 1, 0.25, 1005, 10), today_row])
        after = asyncio.run(ds.daily_rows(TCS))
        assert [r[4] for r in after] == [1000, 1005, 2020] and calls[-1] == ds.HISTORY_START
    finally:
        ds.fetch = original


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
