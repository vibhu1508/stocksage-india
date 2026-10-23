"""Movers: NSE's groups and phases, one shared copy for everyone, and fallbacks when NSE fails."""

import asyncio
import os
import time
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "test")

from routers import market_data as md  # noqa: E402

IST = md.IST
ROW = lambda s, pct, price=100.0: md._mover(s, price, 100.0, pct, 10)  # noqa: E731


def _patch(store: dict, now: datetime, variations=None, pre_open=None, bhav=None):
    calls = {"variations": 0, "pre_open": 0, "bhav": 0}

    async def get(key):
        return store.get(key)

    async def put(key, value, ttl):
        store[key] = value

    def source(name, value):
        async def fetch():
            calls[name] += 1
            if isinstance(value, Exception):
                raise value
            return value() if callable(value) else value
        return fetch

    md.cache_get_json, md.cache_set_json = get, put
    md._nse_variations = source("variations", variations)
    md._nse_pre_open = source("pre_open", pre_open)
    md._bhavcopy_snapshot = source("bhav", bhav)
    md.get_ist_now = lambda: now
    md._movers_locks.clear()
    return calls


def snap(at: datetime, gainers=("TCS",), losers=("INFY",)):
    return {"asOf": at.isoformat(), "groups": {"NIFTY": {
        "gainers": [ROW(s, 1.0) for s in gainers], "losers": [ROW(s, -1.0) for s in losers]}}}


def test_phase_follows_the_clock_and_holidays():
    at = lambda h, m, day=23: datetime(2026, 10, day, h, m, tzinfo=IST)  # noqa: E731 (23 Oct 2026 is a Friday)
    assert [md.market_phase(at(h, m)) for h, m in ((8, 59), (9, 0), (9, 15), (15, 29), (15, 30), (16, 5))] == \
        ["closed", "pre_open", "open", "open", "closing", "closed"]
    assert md.market_phase(at(11, 0, day=24)) == "closed"  # Saturday


def test_one_nse_call_serves_everyone_and_both_lists_share_a_group():
    now = datetime(2026, 10, 23, 11, 0, tzinfo=IST)
    store = {}
    calls = _patch(store, now, variations=snap(now))
    for _ in range(5):
        movers = asyncio.run(md.market_movers("NIFTY"))
    assert calls["variations"] == 1 and movers["phase"] == "open"
    assert [r["symbol"] for r in movers["gainers"]] == ["TCS"] and [r["symbol"] for r in movers["losers"]] == ["INFY"]


def test_yesterdays_lists_are_labelled_closed_and_pre_open_uses_its_own_list():
    yesterday_close = datetime(2026, 10, 22, 16, 0, tzinfo=IST)
    now = datetime(2026, 10, 23, 9, 5, tzinfo=IST)
    store = {}
    _patch(store, now, variations=snap(yesterday_close), pre_open=snap(now, gainers=("SBIN",)))
    pre = asyncio.run(md.market_movers("NIFTY"))
    assert pre["phase"] == "pre_open" and pre["gainers"][0]["symbol"] == "SBIN"

    store.clear()
    _patch(store, now, variations=snap(yesterday_close), pre_open=ValueError("no pre-open session today yet"))
    fallback = asyncio.run(md.market_movers("NIFTY"))
    assert fallback["phase"] == "closed" and fallback["gainers"][0]["symbol"] == "TCS"  # never "pre-open" over old data

    store.clear()
    _patch(store, datetime(2026, 10, 23, 9, 15, 20, tzinfo=IST), variations=snap(yesterday_close))
    assert asyncio.run(md.market_movers("NIFTY"))["phase"] == "closed"  # NSE hasn't published today's list yet


def test_closing_window_turns_closed_once_nse_final_values_are_in():
    store = {}
    _patch(store, datetime(2026, 10, 23, 15, 45, tzinfo=IST), variations=snap(datetime(2026, 10, 23, 15, 44, tzinfo=IST)))
    assert asyncio.run(md.market_movers("NIFTY"))["phase"] == "closing"
    store.clear()
    _patch(store, datetime(2026, 10, 23, 16, 2, tzinfo=IST), variations=snap(datetime(2026, 10, 23, 16, 0, tzinfo=IST)))
    assert asyncio.run(md.market_movers("NIFTY"))["phase"] == "closed"


def test_nse_failure_serves_last_copy_then_bhavcopy():
    now = datetime(2026, 10, 23, 11, 0, tzinfo=IST)
    store = {"movers:variations": {"at": time.time() - 600, "data": snap(now, gainers=("OLD",))}}
    calls = _patch(store, now, variations=RuntimeError("403"), bhav=snap(now, gainers=("BHAV",)))
    assert asyncio.run(md.market_movers("NIFTY"))["gainers"][0]["symbol"] == "OLD"
    assert asyncio.run(md.market_movers("NIFTY"))["gainers"][0]["symbol"] == "OLD"
    assert calls["variations"] == 1  # the stale copy was re-stamped: NSE is asked again only after a minute

    store.clear()
    assert asyncio.run(md.market_movers("NIFTY"))["gainers"][0]["symbol"] == "BHAV" and calls["bhav"] == 1


def test_rank_groups_uses_members_prices_and_drops_flat_stocks():
    rows = [ROW("TCS", 2.0, 2500), ROW("INFY", -1.0, 1500), ROW("PENNY", 9.0, 5), ROW("FLAT", 0.0, 50)]
    groups = md.rank_groups(rows, [ROW("TCS", 2.0, 2500)], {"NIFTY": {"TCS", "INFY", "FLAT"}})
    assert [r["symbol"] for r in groups["NIFTY"]["gainers"]] == ["TCS"]
    assert [r["symbol"] for r in groups["NIFTY"]["losers"]] == ["INFY"]
    assert [r["symbol"] for r in groups["SecLwr20"]["gainers"]] == ["PENNY"]
    assert [r["symbol"] for r in groups["allSec"]["gainers"]] == ["PENNY", "TCS"]
    assert groups["FOSec"]["gainers"][0]["symbol"] == "TCS" and groups["BANKNIFTY"]["gainers"] == []


def test_downsample_keeps_the_last_price():
    line = [float(i) for i in range(400)]
    small = md.downsample(line, 60)
    assert len(small) == 60 and small[0] == 0.0 and small[-1] == 399.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
