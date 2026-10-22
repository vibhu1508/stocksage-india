"""1-minute OHLCV candles from a quote stream, and higher timeframes built from them (plan §5.2)."""

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

IST = timezone(timedelta(hours=5, minutes=30))
SESSION_OPEN = (9, 15)  # NSE buckets (and Dhan's 25m/60m candles) are anchored at 09:15 IST


class CandleBuilder:
    """Candles as [open_time, open, high, low, close, volume], the wire shape of plan §5.4.

    Dhan quotes carry the day's cumulative volume, so a candle's volume is the increase
    in cumulative volume across the ticks that land in it. Pass `current` to resume the
    in-progress candle from seeded history instead of starting it over.
    """

    def __init__(self, interval: int = 60, current: Optional[list] = None):
        self.interval = interval
        self.current: Optional[list] = list(current) if current else None
        self._last_cum: Optional[int] = None

    def update(self, ts: int, price: float, cum_volume: Optional[int] = None) -> Optional[list]:
        """Apply one tick. Returns the candle that just closed when this tick opens a new one."""
        start = ts - ts % self.interval
        volume = 0
        if cum_volume is not None:
            if self._last_cum is not None and cum_volume >= self._last_cum:
                volume = cum_volume - self._last_cum
            self._last_cum = cum_volume

        candle = self.current
        if candle is None or start > candle[0]:
            self.current = [start, price, price, price, price, volume]
            return candle
        if start < candle[0]:
            # Late tick for a minute already closed: drop it; EOD reconciliation repairs the bar.
            return None
        candle[2] = max(candle[2], price)
        candle[3] = min(candle[3], price)
        candle[4] = price
        candle[5] += volume
        return None


def session_open(ts: int) -> int:
    """09:15 IST on the IST day of `ts`."""
    day = datetime.fromtimestamp(ts, IST)
    return int(day.replace(hour=SESSION_OPEN[0], minute=SESSION_OPEN[1], second=0, microsecond=0).timestamp())


def bucket_start(ts: int, minutes: int) -> int:
    """Start of the `minutes`-wide bucket holding `ts`, counted from that day's 09:15 IST."""
    if minutes <= 1:
        return ts - ts % 60
    anchor = session_open(ts)
    width = minutes * 60
    return anchor + (ts - anchor) // width * width


def aggregate(m1: Iterable[list], minutes: int) -> list[list]:
    """Roll sorted 1-minute candles up into `minutes`-wide candles.

    The 1-minute bar stamped 09:15 holds the pre-open auction. Dhan's own 5/15/25/60m bars
    leave it out (their first bar opens at the 09:16 price; checked against REST on
    22 Oct 2026), so we do the same to keep charts identical to the provider's.
    """
    if minutes <= 1:
        return [list(c) for c in m1]
    out: list[list] = []
    for t, o, h, l, c, v in m1:
        t = int(t)
        if t == session_open(t):
            continue
        start = bucket_start(t, minutes)
        if out and out[-1][0] == start:
            bar = out[-1]
            bar[2] = max(bar[2], h)
            bar[3] = min(bar[3], l)
            bar[4] = c
            bar[5] += v
        else:
            out.append([start, o, h, l, c, v])
    return out
