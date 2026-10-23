"""NSE bhavcopy zips kept on disk: each day is downloaded once and read locally after that.

A published bhavcopy never changes, so a saved file is used as-is. A weekend or holiday that NSE
answers with 404 gets a small ".404" marker so it isn't asked for again; a 404 on a trading day
(not published yet, or NSE having a bad moment) is retried on the next request.
Layout: <STOCKSAGE_DATA_DIR>/bhavcopy/{cm,fo}/YYYYMMDD.zip
"""

import io
import os
import threading
import time
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from utils.market_utils import is_market_holiday

ROOT = Path(os.getenv("STOCKSAGE_DATA_DIR", str(Path.home() / "stocksage-data"))) / "bhavcopy"
IST = ZoneInfo("Asia/Kolkata")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/zip",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


def get_zip(kind: str, url_template: str, target_date: date) -> Optional[bytes]:
    """The day's zip bytes ("cm" or "fo"), from disk or NSE; None when that day has no bhavcopy.
    Other HTTP errors raise, so callers keep their own error handling."""
    stamp = target_date.strftime("%Y%m%d")
    path = ROOT / kind / f"{stamp}.zip"
    missing = path.with_suffix(".404")
    if path.exists():
        return path.read_bytes()
    if missing.exists():
        return None

    session = requests.Session()
    session.headers.update(HEADERS)
    session.get("https://www.nseindia.com", timeout=10)  # cookies first
    time.sleep(0.5)
    response = session.get(url_template.format(date=stamp), timeout=30)
    path.parent.mkdir(parents=True, exist_ok=True)
    if response.status_code == 404:
        if target_date < datetime.now(IST).date() and (target_date.weekday() >= 5 or is_market_holiday(target_date)):
            missing.touch()
        return None
    response.raise_for_status()

    content = response.content
    if zipfile.ZipFile(io.BytesIO(content)).testzip() is not None:  # never save a broken download
        raise zipfile.BadZipFile(f"corrupt bhavcopy for {stamp}")
    part = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.part")  # one per writer
    part.write_bytes(content)
    part.replace(path)
    return content
