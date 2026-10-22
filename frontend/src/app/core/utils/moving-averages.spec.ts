import { momentum, movingAverage, trendSignal } from './moving-averages';

describe('moving-average maths', () => {
  const closes = Array.from({ length: 200 }, (_, i) => i + 1); // 1..200, a steady uptrend

  it('averages the last N closes, or null without enough history', () => {
    expect(movingAverage(closes, 50)).toBe(175.5);   // mean of 151..200
    expect(movingAverage(closes, 200)).toBe(100.5);
    expect(movingAverage(closes.slice(0, 199), 200)).toBeNull();
  });

  it('measures momentum against the close N sessions earlier', () => {
    expect(momentum(closes, 10)).toBe(10);
    expect(momentum([5, 4, 3, 2, 1, 0, 1, 2, 3, 4, 2], 10)).toBe(-3);
    expect(momentum([1, 2], 10)).toBeNull();
  });

  it('calls the trend from price and the stacked averages', () => {
    expect(trendSignal(200, 175.5, 150.5, 100.5)).toBe('Bullish');
    // RELIANCE on 22 Oct 2026: below all three, stacked downward.
    expect(trendSignal(1189.9, 1252.78, 1276.82, 1340.04)).toBe('Bearish');
    // TCS on 22 Oct 2026: above the 50 and 200 but the averages are out of order.
    expect(trendSignal(2505.7, 2246.51, 2231.66, 2453.99)).toBe('Mixed');
    expect(trendSignal(100, 90, 80, null)).toBe('N/A');
  });
});
