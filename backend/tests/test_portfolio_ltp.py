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


def test_bse_only_holding_is_priced_from_dhan_in_nse_shape():
    import asyncio
    from routers import strategy_builder

    # Dhan's /marketfeed/quote for SPICEJET (BSE 500285) on 22 Oct 2026, as _cached_dhan_post wraps it.
    dhan = {"data": {"data": {"BSE_EQ": {"500285": {
        "last_price": 8.17, "net_change": 0.25, "volume": 4963266, "average_price": 8.01,
        "52_week_high": 40.59, "52_week_low": 0, "last_trade_time": "22/10/2026 15:59:57",
        "ohlc": {"open": 7.92, "close": 7.92, "high": 8.3, "low": 7.72},
    }}}}}
    entry = {"symbol": "SPICEJET", "name": "Spicejet", "isin": "INE285B01017", "nse": None,
             "bse": {"sid": "500285", "symbol": "SPICEJET", "series": "B"}}

    async def fake_dhan(endpoint, payload, kind):
        assert (endpoint, payload) == ("/marketfeed/quote", {"BSE_EQ": [500285]})
        return dhan

    original = strategy_builder.dm._cached_dhan_post
    strategy_builder.dm._cached_dhan_post = fake_dhan
    try:
        quote = asyncio.run(strategy_builder._bse_quote_in_nse_shape(entry))
    finally:
        strategy_builder.dm._cached_dhan_post = original
    first = quote["equityResponse"][0]
    assert first["exchange"] == "BSE"
    assert (first["metaData"]["previousClose"], first["metaData"]["pChange"]) == (7.92, 3.16)
    assert first["priceInfo"]["yearLow"] is None  # Dhan's 0 means unknown, not a price
    assert _extract_ltp(quote) == 8.17  # what the portfolio reads when the feed has no price yet


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
