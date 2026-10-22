"""Company list built from Dhan's detailed instrument list. Run: python -m tests.test_instruments (from backend/), or pytest."""

from services.instruments import build_instruments


def _row(exch, sid, isin, symbol, kind="ES", series="EQ", name=""):
    return {"EXCH_ID": exch, "SEGMENT": "E", "SECURITY_ID": sid, "ISIN": isin, "INSTRUMENT_TYPE": kind,
            "UNDERLYING_SYMBOL": symbol, "SERIES": series, "DISPLAY_NAME": name or symbol.title(), "SYMBOL_NAME": symbol}


# Real rows (trimmed) from Dhan's list on 22 Oct 2026.
ROWS = [
    _row("BSE", "500325", "INE002A01018", "RELIANCE", series="A", name="Reliance Industries"),
    _row("NSE", "2885", "INE002A01018", "RELIANCE", name="Reliance Industries"),
    _row("BSE", "500285", "INE285B01017", "SPICEJET", series="B", name="Spicejet"),           # BSE-only
    _row("NSE", "10253", "INE332S01011", "EMKAYTOOLS", series="SM"),                          # NSE SME
    _row("NSE", "10051", "INF200KA1F35", "SFMP6DD", kind="MF", series="MF"),                   # fund units: out
    _row("NSE", "19813", "INF204KB14I2", "NIFTYBEES", kind="ETF"),                             # ETF: in
    _row("NSE", "1", "INE002A07015", "RELNCD", kind="DBT", series="N1"),                       # debt: out
    _row("NSE", "999", "INE123A01016", "FOCUS"),                                               # NSE company FOCUS
    _row("BSE", "532000", "INE987Z01011", "FOCUS", series="X"),                                # different BSE-only FOCUS
]


def test_one_entry_per_company_with_both_listings():
    out = build_instruments(ROWS)
    rel = out["RELIANCE"]
    assert (rel["isin"], rel["name"], rel["nse"]["sid"], rel["bse"]["sid"]) == ("INE002A01018", "Reliance Industries", "2885", "500325")


def test_keeps_shares_and_etfs_only():
    assert set(build_instruments(ROWS)) == {"RELIANCE", "SPICEJET", "EMKAYTOOLS", "NIFTYBEES", "FOCUS", "BSE:FOCUS"}


def test_bse_only_keys_and_clashes():
    out = build_instruments(ROWS)
    assert out["SPICEJET"]["nse"] is None and out["SPICEJET"]["bse"]["sid"] == "500285"
    # The NSE company keeps the plain symbol; the unrelated BSE-only one gets an exchange prefix.
    assert out["FOCUS"]["isin"] == "INE123A01016"
    assert (out["BSE:FOCUS"]["isin"], out["BSE:FOCUS"]["symbol"]) == ("INE987Z01011", "FOCUS")


def test_search_ranks_and_badges():
    import os
    os.environ.setdefault("SECRET_KEY", "test-only-secret")
    from routers.stocks import rank_search

    out = build_instruments(ROWS)
    # Exact symbol first, then the BSE-only company with the same symbol; badges list the exchanges.
    assert [(r["symbol"], r["exchanges"]) for r in rank_search(out, "focus", 5)] == [("FOCUS", ["NSE"]), ("BSE:FOCUS", ["BSE"])]
    assert rank_search(out, "RELIANCE", 1)[0]["exchanges"] == ["NSE", "BSE"]
    assert [r["symbol"] for r in rank_search(out, "spice", 5)] == ["SPICEJET"]  # BSE-only is searchable
    assert rank_search(out, "   ", 5) == []


def test_index_constituent_moves_and_index_search():
    import os
    os.environ.setdefault("SECRET_KEY", "test-only-secret")
    from routers.stocks import INDEX_CONSTITUENTS, constituent_moves, rank_search
    from services.instruments import build_indices

    # NIFTY BANK members (NSE archive CSV) and their 22 Oct 2026 bhavcopy close / previous close.
    members = [{"symbol": "HDFCBANK", "name": "HDFC Bank Ltd.", "industry": "Financial Services"},
               {"symbol": "AUBANK", "name": "AU Small Finance Bank Ltd.", "industry": "Financial Services"},
               {"symbol": "NEWLIST", "name": "Listed Today Ltd.", "industry": "Financial Services"}]
    out = constituent_moves(members, {"HDFCBANK": (694.05, 706.95), "AUBANK": (720.0, 710.0)})
    assert [(r["symbol"], r["pct"]) for r in out["rows"]] == [("AUBANK", 1.41), ("HDFCBANK", -1.82), ("NEWLIST", None)]
    assert (out["advances"], out["declines"], out["unchanged"]) == (1, 1, 0)
    assert out["industries"] == [{"industry": "Financial Services", "count": 2, "avgPct": -0.21}]

    # Indices are keyed apart from stocks, found without spaces, and listed before same-rank stocks.
    rows = [{"SEGMENT": "I", "EXCH_ID": "NSE", "UNDERLYING_SYMBOL": "NIFTY", "DISPLAY_NAME": "Nifty 50", "SECURITY_ID": "13"},
            {"SEGMENT": "I", "EXCH_ID": "BSE", "UNDERLYING_SYMBOL": "SENSEX", "DISPLAY_NAME": "Sensex", "SECURITY_ID": "51"}]
    indices = build_indices(rows)
    assert indices["INDEX:NIFTY"] == {"symbol": "NIFTY", "name": "Nifty 50", "exchange": "NSE", "sid": "13"}
    hit = rank_search(build_instruments(ROWS), "nifty50", 3, indices)[0]
    assert (hit["symbol"], hit["kind"], hit["exchanges"]) == ("INDEX:NIFTY", "index", ["NSE"])
    assert rank_search({}, "sensex", 1, indices)[0]["symbol"] == "INDEX:SENSEX"
    # Every mapped index points at a real Dhan symbol name and an NSE archive file.
    assert INDEX_CONSTITUENTS["NIFTY PVT BANK"] == ("NIFTY PRIVATE BANK", "nifty_privatebank")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
