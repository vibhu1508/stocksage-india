"""NSE holidays: today's response format, and at most one NSE request a day even when it fails."""

from datetime import date

from utils import market_utils as mu


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def _fake_session(payload, calls):
    class Session:
        def get(self, url, **kwargs):
            calls.append(url)
            return _Response(payload)
    return Session


def _reset():
    mu._cached_holidays, mu._last_fetch_date = set(), None


def test_reads_the_cash_market_segment_and_caches_for_the_day():
    calls, original = [], mu.requests.Session
    mu.requests.Session = _fake_session({"CM": [{"tradingDate": "20-Oct-2026"}], "FO": [{"tradingDate": "01-Jan-2030"}]}, calls)
    _reset()
    try:
        assert mu.is_market_holiday(date(2026, 10, 20)) and not mu.is_market_holiday(date(2026, 10, 23))
        mu.is_market_holiday(date(2026, 10, 22))
        assert len(calls) == 2  # home page + holiday API, once for the day
    finally:
        mu.requests.Session = original
        _reset()


def test_an_unusable_answer_uses_the_fallback_without_asking_again():
    calls, original = [], mu.requests.Session
    mu.requests.Session = _fake_session({"something": "else"}, calls)
    _reset()
    try:
        assert mu.is_market_holiday(date(2026, 11, 10))  # Diwali, from the built-in list
        for _ in range(5):
            mu.is_market_holiday(date(2026, 10, 23))
        assert len(calls) == 2
    finally:
        mu.requests.Session = original
        _reset()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
