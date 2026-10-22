"""1-minute OHLCV candles from a quote stream (plan §5.2 step 4)."""

from typing import Optional


class CandleBuilder:
    """Candles as [open_time, open, high, low, close, volume], the wire shape of plan §5.4.

    Dhan quotes carry the day's cumulative volume, so a candle's volume is the increase
    in cumulative volume across the ticks that land in it.
    """

    def __init__(self, interval: int = 60):
        self.interval = interval
        self.current: Optional[list] = None
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
