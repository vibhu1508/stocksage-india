"""Dhan per-account rate gate. Run: python -m tests.test_dhan_gate (from backend/), or pytest."""

import asyncio
import os
import time

os.environ.setdefault("SECRET_KEY", "test-only-secret")
os.environ["REDIS_URL"] = ""

from routers import dhan_market as dm  # noqa: E402


def test_quote_calls_are_spaced_and_other_classes_are_not_blocked():
    dm.DHAN_MIN_GAP_SECONDS = (("/marketfeed/", 0.2), ("/charts/", 0.0))
    starts: dict[str, list[float]] = {"quote": [], "charts": []}

    async def call(endpoint, bucket):
        async with dm._dhan_slot(endpoint):
            starts[bucket].append(time.monotonic())

    async def main():
        await asyncio.gather(*[call("/marketfeed/ltp", "quote") for _ in range(4)],
                             *[call("/charts/intraday", "charts") for _ in range(4)])

    t0 = time.monotonic()
    asyncio.run(main())
    gaps = [b - a for a, b in zip(starts["quote"], starts["quote"][1:])]
    assert all(g >= 0.19 for g in gaps), gaps          # never two quote calls inside the gap
    assert max(starts["charts"]) - t0 < 0.1             # a different class doesn't queue behind quotes


def test_server_errors_never_show_their_detail():
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    import main

    app = FastAPI()
    app.add_exception_handler(main.StarletteHTTPException, main.hide_server_error_details)

    @app.get("/boom")
    def boom():
        raise HTTPException(status_code=502, detail="NSE API Error: https://www.nseindia.com/api/x 404")

    @app.get("/missing")
    def missing():
        raise HTTPException(status_code=404, detail="Unknown index")

    client = TestClient(app)
    r = client.get("/boom")
    assert (r.status_code, r.json()) == (502, {"detail": "Internal server error. Please try again shortly."})
    assert client.get("/missing").json() == {"detail": "Unknown index"}  # client errors keep their message


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
