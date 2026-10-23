"""Browser caching rules: shared market data is cached briefly, past dates for a day, personal data never."""

import os

os.environ.setdefault("SECRET_KEY", "test")
os.environ["REDIS_URL"] = ""

from main import cache_control_for  # noqa: E402

TODAY = "2026-10-23"


def test_rules():
    assert cache_control_for("/api/market/top-stocks", "", TODAY) == "private, max-age=30"
    assert cache_control_for("/api/stocks/bhavcopy/2026-10-22", "", TODAY) == "private, max-age=86400"
    assert cache_control_for("/api/stocks/bhavcopy/2026-10-23", "", TODAY) == "private, max-age=300"
    assert cache_control_for("/api/stocks/compare", "date1=2026-01-02&date2=2026-10-22", TODAY) == "private, max-age=86400"
    assert cache_control_for("/api/stocks/compare", "date1=2026-01-02&date2=2026-10-23", TODAY) == "private, max-age=300"
    assert cache_control_for("/api/fo/data/latest", "", TODAY) == "private, max-age=300"
    assert cache_control_for("/api/portfolio/holdings", "", TODAY) == "no-store"
    assert cache_control_for("/api/market/dhan/chart/history", "", TODAY) is None
    assert cache_control_for("/api/stocks/index/NIFTY/live", "", TODAY) == "private, max-age=10"


def test_middleware_sets_header_only_on_success():
    from fastapi.testclient import TestClient
    import main

    @main.app.get("/api/stocks/compare-probe")
    async def probe():
        return {"ok": True}

    client = TestClient(main.app)
    assert client.get("/api/stocks/compare-probe").headers["cache-control"] == "private, max-age=300"
    assert "cache-control" not in client.get("/api/stocks/index/NIFTY").headers


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
