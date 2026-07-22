"""
Trusted-source news for the StockSage AI assistant.

Only news from an explicit whitelist of trusted publishers is surfaced. We use
Google News RSS purely as an index/search, then keep ONLY items whose publisher
is on the whitelist — everything else is dropped.
"""

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from xml.etree import ElementTree

import httpx

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

logger = logging.getLogger(__name__)

# publisher domain (suffix) -> display name. Only these sources are trusted.
TRUSTED = {
    "moneycontrol.com": "MoneyControl",
    "timesofindia.indiatimes.com": "Times of India",
    "indiatimes.com": "Times of India",
    "rediff.com": "Rediff",
    "angelone.in": "Angel One",
    "dhan.co": "Dhan",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _domain(url: str) -> str:
    m = re.search(r"https?://([^/]+)", url or "")
    host = (m.group(1).lower() if m else "")
    return host[4:] if host.startswith("www.") else host


def _trusted_name(source_url: str) -> str | None:
    d = _domain(source_url)
    for dom, name in TRUSTED.items():
        if d == dom or d.endswith("." + dom):
            return name
    return None


async def fetch_trusted_news(query: str, limit: int = 6) -> list[dict]:
    """Return up to `limit` recent news items (from trusted publishers only) for the query."""
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(url, headers=_HEADERS)
        root = ElementTree.fromstring(resp.text)
    except Exception:
        logger.exception("news fetch failed for %s", query)
        return []

    items: list[dict] = []
    for item in root.iter("item"):
        src_el = item.find("source")
        if src_el is None:
            continue
        name = _trusted_name(src_el.get("url", ""))
        if not name:
            continue  # drop anything not on the trusted whitelist

        title = (item.findtext("title") or "").strip()
        src_text = (src_el.text or "").strip()
        if src_text and title.endswith(f"- {src_text}"):
            title = title[: -(len(src_text) + 2)].strip()

        published = (item.findtext("pubDate") or "").strip()
        try:
            when = parsedate_to_datetime(published) or _EPOCH
        except (TypeError, ValueError):
            when = _EPOCH

        items.append({
            "title": title,
            "source": name,
            "published": published,
            "link": (item.findtext("link") or "").strip(),
            "_when": when,
        })

    # Freshest trusted items first.
    items.sort(key=lambda it: it["_when"], reverse=True)
    for it in items:
        it.pop("_when", None)
    return items[:limit]
