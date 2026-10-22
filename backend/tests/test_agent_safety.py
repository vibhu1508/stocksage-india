"""Safety checks for the AI assistant. Run: python -m tests.test_agent_safety (from backend/), or pytest."""

import json
import os

os.environ.setdefault("SECRET_KEY", "test-only-secret")

from services.agent import _writer_data  # noqa: E402
from services.portfolio_actions import record_equity_holding  # noqa: E402


def test_writer_data_keeps_numbers_when_news_is_long():
    news = [
        {"title": f"Story {i}", "source": "Mint", "link": "https://news.google.com/" + "x" * 400, "snippet": "y" * 700}
        for i in range(6)
    ]
    tool_data = [{"tool": "get_sentiment", "result": {
        "symbol": "TCS", "recent_news": news,
        "index_trend": [{"symbol": "NIFTY 50", "pct_change": -0.42}],
        "stock_pct_change_today": 1.37,
    }}]
    out = json.loads(_writer_data(tool_data))  # must stay valid JSON
    res = out[0]["result"]
    assert res["stock_pct_change_today"] == 1.37
    assert res["index_trend"][0]["pct_change"] == -0.42
    assert all("link" not in n for n in res["recent_news"])
    assert "link" in news[0], "caller's list (used later by elaborate_news) must not be mutated"


def test_writer_data_trims_long_article():
    tool_data = [{"tool": "elaborate_news", "result": {"title": "T", "content": "z" * 20000}}]
    out = _writer_data(tool_data, budget=6000)
    assert len(out) < 6000 and json.loads(out)[0]["result"]["title"] == "T"


def test_record_holding_rejects_bad_values_before_db():
    for qty, price in [(0, 100), (-5, 100), (10, 0), (10, -1), ("ten", 100)]:
        assert record_equity_holding(1, "TCS", qty, price) == {"ok": False, "error": "invalid holding"}
    assert record_equity_holding(1, " ", 10, 100)["ok"] is False


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
