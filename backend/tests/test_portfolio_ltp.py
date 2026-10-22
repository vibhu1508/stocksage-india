"""Portfolio price extraction. Run: python -m tests.test_portfolio_ltp (from backend/), or pytest."""

import os

os.environ.setdefault("SECRET_KEY", "test-only-secret")

from routers.portfolio import _extract_ltp  # noqa: E402

# Trimmed shape of NSE's GetQuoteApi response; priceInfo comes first and has no last price.
NSE_QUOTE = {"equityResponse": [{
    "priceInfo": {"yearHigh": 1611.8, "yearLow": 1114.85},
    "orderBook": {"buyPrice1": 1186.9, "lastPrice": 1186.9},
    "metaData": {"open": 1206.2, "closePrice": 0},
    "tradeInfo": {"lastPrice": 1186.9},
}]}


def test_never_returns_an_unrelated_number():
    assert _extract_ltp(NSE_QUOTE) == 1186.9  # was 1611.8, the 52-week high
    assert _extract_ltp({"priceInfo": {"yearHigh": 1611.8}}) is None


def test_option_legs_and_scalars_still_work():
    assert _extract_ltp({"CE": {"strikePrice": 25000, "lastPrice": 12.5}}) == 12.5
    assert _extract_ltp("101.5") == 101.5
    assert _extract_ltp(0) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
