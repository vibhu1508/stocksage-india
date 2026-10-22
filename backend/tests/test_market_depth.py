"""Market depth parsing. Run: python -m tests.test_market_depth (from backend/), or pytest."""

import os
import struct

os.environ.setdefault("SECRET_KEY", "test-only-secret")

from fastapi import HTTPException  # noqa: E402

from routers.dhan_market import _extract_depth_from_quote, _parse_full_depth_packet  # noqa: E402

ZERO = {"quantity": 0, "orders": 0, "price": 0}
# RELIANCE from Dhan's /marketfeed/quote at 21:30 IST on 22 Oct: one unmatched closing order, rest padding.
AFTER_HOURS = {"NSE_EQ": {"2885": {"last_price": 1184.5, "depth": {
    "buy": [ZERO] * 5,
    "sell": [{"quantity": 184725, "orders": 96, "price": 1184.5}] + [ZERO] * 4,
}}}}


def test_after_hours_book_keeps_zero_levels_so_the_table_keeps_its_shape():
    depth = _extract_depth_from_quote(AFTER_HOURS, "NSE_EQ", "2885", 20)
    assert depth["buy"] == [{"price": 0.0, "quantity": 0, "orders": 0}] * 5
    assert depth["sell"][0] == {"price": 1184.5, "quantity": 184725, "orders": 96} and len(depth["sell"]) == 5


def test_missing_depth_is_an_error():
    try:
        _extract_depth_from_quote({"NSE_EQ": {"2885": {"last_price": 1}}}, "NSE_EQ", "2885", 20)
        raise AssertionError("expected a 502 for a response without depth")
    except HTTPException as exc:
        assert exc.status_code == 502


def test_full_depth_packet_rows():
    # Header as Dhan sends it (200-level: bytes 8-11 are the row count), then price f64, qty u32, orders u32.
    rows = struct.pack("<dII", 1184.5, 300, 4) + struct.pack("<dII", 0.0, 0, 0)
    packet = struct.pack("<HBBiI", 12 + len(rows), 51, 1, 2885, 2) + rows
    assert _parse_full_depth_packet(packet) == ("sell", [{"price": 1184.5, "quantity": 300, "orders": 4}])
    assert _parse_full_depth_packet(struct.pack("<HBBiI", 12, 41, 1, 2885, 0)) == ("buy", [])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
