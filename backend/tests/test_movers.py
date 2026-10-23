"""Shared movers cache: one NSE call per minute for everyone, and a fallback when NSE fails."""

import asyncio
import os
import time

os.environ.setdefault("SECRET_KEY", "test")

from routers import market_data as md  # noqa: E402


def _patch(store: dict, nse, bhav):
    calls = {"nse": 0, "bhav": 0}

    async def get(key):
        return store.get(key)

    async def put(key, value, ttl):
        store[key] = value

    async def fake_nse():
        calls["nse"] += 1
        return nse()

    async def fake_bhav(kind):
        calls["bhav"] += 1
        return bhav

    md.cache_get_json, md.cache_set_json = get, put
    md._nse_gainers, md._bhavcopy_movers = fake_nse, fake_bhav
    md._market_hours_now = lambda: True
    return calls


def test_one_nse_call_serves_everyone_within_a_minute():
    store = {}
    calls = _patch(store, lambda: [{"symbol": "TCS"}], [])
    for _ in range(5):
        assert asyncio.run(md.shared_movers("gainers")) == [{"symbol": "TCS"}]
    assert calls["nse"] == 1


def test_nse_failure_serves_last_copy_then_bhavcopy_and_retries_in_a_minute():
    def down():
        raise RuntimeError("403")

    store = {"movers:gainers": {"at": time.time() - 600, "items": [{"symbol": "OLD"}]}}
    calls = _patch(store, down, [{"symbol": "BHAV"}])
    assert asyncio.run(md.shared_movers("gainers")) == [{"symbol": "OLD"}]
    assert asyncio.run(md.shared_movers("gainers")) == [{"symbol": "OLD"}]
    assert calls["nse"] == 1  # the stale copy was re-stamped: NSE is asked again only after a minute
    assert 0 < time.time() - store["movers:gainers"]["at"] <= md.MOVERS_FRESH_LIVE

    store.clear()
    assert asyncio.run(md.shared_movers("gainers")) == [{"symbol": "BHAV"}]
    assert calls["bhav"] == 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
