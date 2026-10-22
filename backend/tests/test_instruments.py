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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
