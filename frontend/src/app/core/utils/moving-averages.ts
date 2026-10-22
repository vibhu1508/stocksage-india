/** Moving-average trend maths shared by the screener and the stock page, on daily closes. */

export type TrendSignal = 'Bullish' | 'Bearish' | 'Mixed' | 'N/A';

/** Average of the last `length` closes, or null without enough history. */
export function movingAverage(closes: number[], length: number): number | null {
  if (closes.length < length) return null;
  const window = closes.slice(-length);
  return window.every(Number.isFinite) ? window.reduce((a, b) => a + b, 0) / length : null;
}

/** Change of the last close against the close `period` sessions earlier. */
export function momentum(closes: number[], period: number): number | null {
  if (closes.length <= period) return null;
  const latest = closes[closes.length - 1];
  const earlier = closes[closes.length - 1 - period];
  return Number.isFinite(latest) && Number.isFinite(earlier) ? latest - earlier : null;
}

/** Bullish when price > MA50 > MA100 > MA200, Bearish when fully reversed, else Mixed. */
export function trendSignal(close: number | null, ma50: number | null, ma100: number | null, ma200: number | null): TrendSignal {
  if (close == null || ma50 == null || ma100 == null || ma200 == null) return 'N/A';
  if (close > ma50 && ma50 > ma100 && ma100 > ma200) return 'Bullish';
  if (close < ma50 && ma50 < ma100 && ma100 < ma200) return 'Bearish';
  return 'Mixed';
}
