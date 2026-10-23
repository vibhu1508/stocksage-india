"""Evening top-up: add the day's candle to every NSE stock in the daily store, from NSE's bhavcopy.

Run from backend/:  python -m scripts.daily_topup   (a systemd timer runs it on weekday evenings)
The bhavcopy's FinInstrmId is NSE's token, the same number as the stock's NSE_EQ security id.
A stock is only topped up when its last stored day is the previous session and that close agrees
with the bhavcopy's previous close; otherwise (a gap, or a split/bonus that changed the previous
close) its check is cleared, so its next view refetches from the provider and repairs it.
"""

import csv
import io
import logging
import sys
import zipfile
from datetime import date, datetime, time

from dotenv import load_dotenv

load_dotenv()

from routers.stocks import BASE_URL  # noqa: E402
from services import bhavcopy_archive, daily_store  # noqa: E402
from utils.market_utils import IST, get_latest_market_date  # noqa: E402

logger = logging.getLogger("scripts.daily_topup")
SEG = "NSE_EQ"


def plan(bhav_rows: list[dict], stored: dict[str, tuple[int, float]], trade_day: date, prev_day: date):
    """-> ({sid: candle row} to add, [sid] whose history must be re-checked)."""
    today, prev = daily_store.day_stamp(trade_day), daily_store.day_stamp(prev_day)
    add, recheck = {}, []
    for r in bhav_rows:
        sid = (r.get("FinInstrmId") or "").strip()
        if sid not in stored or r.get("TradDt") != trade_day.isoformat():
            continue
        last_day, last_close = stored[sid]
        if last_day >= today:
            continue  # already has the day (the provider answered first)
        try:
            o, h, l, c, pc = (float(r[k]) for k in ("OpnPric", "HghPric", "LwPric", "ClsPric", "PrvsClsgPric"))
            v = int(float(r.get("TtlTradgVol") or 0))
        except (KeyError, ValueError):
            continue
        if last_day != prev or not last_close or abs(pc - last_close) / last_close > daily_store.SPLIT_TOLERANCE:
            recheck.append(sid)
        else:
            add[sid] = (today, o, h, l, c, v)
    return add, recheck


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    trade_day = get_latest_market_date(datetime.now(IST))
    prev_day = get_latest_market_date(datetime.combine(trade_day, time(0), IST))
    content = bhavcopy_archive.get_zip("cm", BASE_URL, trade_day)
    if content is None:
        logger.warning("no bhavcopy for %s yet", trade_day)
        return 1
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        rows = list(csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8")))

    add, recheck = plan(rows, daily_store.latest_closes(SEG), trade_day, prev_day)
    for sid, row in add.items():
        daily_store.upsert(SEG, sid, [row], "bhavcopy")
        daily_store.mark_checked(SEG, sid, trade_day.isoformat())
    for sid in recheck:
        daily_store.clear_checked(SEG, sid)
    logger.info("%s: added %d candles, %d stocks left for a provider re-check", trade_day, len(add), len(recheck))
    return 0


if __name__ == "__main__":
    sys.exit(main())
