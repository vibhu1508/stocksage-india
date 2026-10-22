"""
Dhan live market feed (v2): connection URL, subscribe frames and binary packet parsing.

Protocol only — no I/O — so it can be unit-tested and reused by market-ingest.
Source: https://dhanhq.co/docs/v2/live-market-feed/ and https://dhanhq.co/docs/v2/annexure/
All packets are little-endian, with an 8-byte header: code, message length, segment, security id.
"""

import struct
from typing import Iterator, Optional
from urllib.parse import urlencode

FEED_URL = "wss://api-feed.dhan.co"
SUBSCRIBE_QUOTE = 17
MAX_PER_SUBSCRIBE = 100  # Dhan's cap per subscribe message (5,000 per connection, 5 connections)

SEGMENTS = {
    0: "IDX_I", 1: "NSE_EQ", 2: "NSE_FNO", 3: "NSE_CURRENCY",
    4: "BSE_EQ", 5: "MCX_COMM", 7: "BSE_CURRENCY", 8: "BSE_FNO",
}

CURRENCY_SEGMENTS = {3, 7}

# Disconnect reasons that retrying with the same token cannot fix: stop and alert the operator.
FATAL_DISCONNECT = {
    806: "data APIs not subscribed",
    807: "access token expired",
    808: "authentication failed",
    809: "access token invalid",
    810: "client ID invalid",
}

# Dhan's last-trade-time is IST wall-clock seconds encoded as epoch (UTC + 5:30), measured live
# on 2026-10-22. Normalise to true UTC epoch here so nothing downstream stores shifted time.
DHAN_LTT_OFFSET = 19800

_HEADER = struct.Struct("<BHBi")  # response code, message length, exchange segment, security id
_TICKER = struct.Struct("<fi")  # ltp, ltt
_QUOTE = struct.Struct("<fhifiiiffff")  # ltp, ltq, ltt, atp, volume, sell qty, buy qty, open, close, high, low
_PREV_CLOSE = struct.Struct("<fi")  # previous close, previous OI
_DISCONNECT = struct.Struct("<h")  # reason code


def feed_url(token: str, client_id: str) -> str:
    return f"{FEED_URL}?{urlencode({'version': 2, 'token': token, 'clientId': client_id, 'authType': 2})}"


def subscribe_frames(instruments: list[tuple[str, str]], request_code: int = SUBSCRIBE_QUOTE) -> list[dict]:
    """[(segment, security_id), ...] -> subscribe messages of at most 100 instruments each."""
    frames = []
    for i in range(0, len(instruments), MAX_PER_SUBSCRIBE):
        chunk = instruments[i:i + MAX_PER_SUBSCRIBE]
        frames.append({
            "RequestCode": request_code,
            "InstrumentCount": len(chunk),
            "InstrumentList": [{"ExchangeSegment": seg, "SecurityId": str(sid)} for seg, sid in chunk],
        })
    return frames


def iter_packets(frame: bytes) -> Iterator[bytes]:
    """Split one WebSocket message into packets using each header's length field."""
    offset = 0
    while offset + _HEADER.size <= len(frame):
        _, length, _, _ = _HEADER.unpack_from(frame, offset)
        if length < _HEADER.size or offset + length > len(frame):
            # Length doesn't describe a whole packet here; treat the rest as one packet.
            yield frame[offset:]
            return
        yield frame[offset:offset + length]
        offset += length


def parse_packet(packet: bytes) -> Optional[dict]:
    """Decode one packet into a plain dict, or None for packet types we don't use."""
    if len(packet) < _HEADER.size:
        return None
    code, _, segment, security_id = _HEADER.unpack_from(packet)
    base = {"segment": SEGMENTS.get(segment, str(segment)), "security_id": str(security_id)}
    # Prices arrive as float32 (2495.4 -> 2495.3999); currency quotes in 4 decimals, the rest in 2.
    decimals = 4 if segment in CURRENCY_SEGMENTS else 2

    if code == 4 and len(packet) >= _HEADER.size + _QUOTE.size:
        ltp, ltq, ltt, atp, volume, _, _, day_open, day_close, day_high, day_low = _QUOTE.unpack_from(packet, 8)
        return {
            **base, "type": "quote", "ltp": round(ltp, decimals), "ltq": ltq, "ltt": ltt - DHAN_LTT_OFFSET,
            "atp": round(atp, decimals), "volume": volume, "open": round(day_open, decimals),
            "high": round(day_high, decimals), "low": round(day_low, decimals), "close": round(day_close, decimals),
        }
    if code == 2 and len(packet) >= _HEADER.size + _TICKER.size:
        ltp, ltt = _TICKER.unpack_from(packet, 8)
        return {**base, "type": "ticker", "ltp": round(ltp, decimals), "ltt": ltt - DHAN_LTT_OFFSET}
    if code == 6 and len(packet) >= _HEADER.size + _PREV_CLOSE.size:
        prev_close, _ = _PREV_CLOSE.unpack_from(packet, 8)
        return {**base, "type": "prev_close", "prev_close": round(prev_close, decimals)}
    if code == 50 and len(packet) >= _HEADER.size + _DISCONNECT.size:
        (reason,) = _DISCONNECT.unpack_from(packet, 8)
        return {**base, "type": "disconnect", "reason": reason}
    return None
