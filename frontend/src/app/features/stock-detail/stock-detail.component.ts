import { AfterViewInit, Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import {
  AreaSeries,
  BaselineSeries,
  BarSeries,
  BarData,
  CandlestickData,
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  LineData,
  LineSeries,
  MouseEventParams,
  Time,
  UTCTimestamp,
  createChart,
} from 'lightweight-charts';
import { LucideAngularModule } from 'lucide-angular';

import { StrategyService, YearwiseDataPoint } from '../../core/services/strategy.service';
import { IndexAnalysis, StockService } from '../../core/services/stock.service';
import { IndexOverviewComponent } from './index-overview/index-overview.component';
import { AnnouncementService, NSEAnnouncement } from '../../core/services/announcement.service';
import { ThemeService } from '../../core/services/theme.service';
import { PortfolioService } from '../../core/services/portfolio.service';
import {
  ChartTimeframe,
  DhanChartRequest,
  DhanDepthLevel,
  DhanLiveChartService,
  depthNote,
} from '../../core/services/dhan-live-chart.service';
import { LiveQuote, MarketStreamMessage, MarketStreamRequest, MarketStreamService, StreamCandle } from '../../core/services/market-stream.service';
import { FlashDirective } from '../../shared/directives/flash.directive';
import { shortCompanyName } from '../../shared/pipes/short-name.pipe';
import { CompanyLogoComponent } from '../../shared/components/company-logo/company-logo.component';
import { TrendSignal, momentum, movingAverage, trendSignal } from '../../core/utils/moving-averages';

const IST_OFFSET_SECONDS = 19800;

const toCandle = (c: StreamCandle): CandlestickData => ({
  time: c[0] as UTCTimestamp, open: c[1], high: c[2], low: c[3], close: c[4],
});

type ChartDisplayType = 'candlestick' | 'line' | 'bar' | 'area' | 'baseline';

interface Technicals {
  signal: TrendSignal;
  summary: string;
  /** gapPct: how far price is above (+) or below (-) the average; barPct: half-bar width, 0-50. */
  averages: Array<{ days: number; value: number | null; gapPct: number | null; barPct: number }>;
  momentum: number | null;
  momentumPct: number | null;
  sparkPath: string;
}

@Component({
  selector: 'app-stock-detail',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, LucideAngularModule, FlashDirective, CompanyLogoComponent, IndexOverviewComponent],
  templateUrl: './stock-detail.component.html',
  styleUrl: './stock-detail.component.scss',
})
export class StockDetailComponent implements OnInit, AfterViewInit, OnDestroy {
  symbol = '';
  loading = true;
  error = '';

  quote: any = null;
  indexData: IndexAnalysis | null = null;  // set when the page shows an index (symbol "INDEX:<symbol>")
  announcements: NSEAnnouncement[] = [];
  announcementsLoading = false;
  performanceData: YearwiseDataPoint | null = null;
  performanceLoading = false;

  liveTimeframe: ChartTimeframe = '5';
  liveChartLoading = false;
  liveChartError = '';
  liveChartUpdatedAt: Date | null = null;
  liveTransportStatus: 'idle' | 'connecting' | 'ws' | 'polling' | 'closed' = 'idle';
  liveLastPrice = 0;
  liveCandleCount = 0;
  liveResolvedTimeframe: ChartTimeframe = '5';
  chartType: ChartDisplayType = 'candlestick';
  dailyRange: '1D' | '5D' | '1M' | '3M' | '6M' | '1Y' | '2Y' | '5Y' | '10Y' | 'MAX' = 'MAX';
  readonly dailyRangeOptions: Array<'1D' | '5D' | '1M' | '3M' | '6M' | '1Y' | '2Y' | '5Y' | '10Y' | 'MAX'> =
    ['1D', '5D', '1M', '3M', '6M', '1Y', '2Y', '5Y', '10Y', 'MAX'];
  customFromDate = '';
  customToDate = '';
  customRangeError = '';
  /** Neutral status (market closed / showing last session / historical range) — never styled as an error. */
  sessionNotice = '';
  /** Collapsible custom-range panel. */
  showCustomPanel = false;
  /** True while showing a static historical window instead of the live session. */
  historyMode = false;
  historyLoading = false;
  /** Interval used by the custom range panel; independent of the live timeframe. */
  customInterval: ChartTimeframe = '5';
  readonly customIntervalOptions: Array<{ value: ChartTimeframe; label: string }> = [
    { value: '1', label: '1m' },
    { value: '5', label: '5m' },
    { value: '15', label: '15m' },
    { value: '25', label: '25m' },
    { value: '60', label: '1h' },
    { value: 'D', label: '1D' },
  ];
  quickAddQty = 1;
  quickAddAvgPrice = '';
  quickAddSaving = false;
  quickAddError = '';
  quickAddSuccess = '';
  marketDepthLoading = false;
  marketDepthError = '';
  marketDepthNote = '';
  marketDepthLimit = 20;
  marketDepthBuy: DhanDepthLevel[] = [];
  marketDepthSell: DhanDepthLevel[] = [];
  hoveredCandle: CandlestickData | null = null;
  lastVisibleCandle: CandlestickData | null = null;

  private routeSub?: Subscription;
  private chartApi: IChartApi | null = null;
  private mainSeries: ISeriesApi<any> | null = null;
  private liveCandles: CandlestickData[] = [];
  private resizeObserver: ResizeObserver | null = null;
  private liveSub: Subscription | null = null;
  private chartLoadSub: Subscription | null = null;
  private indicatorSub: Subscription | null = null;
  indicatorsLoading = false;
  indicatorsError = false;  // daily candles failed: say so instead of hiding the panel
  /** Live last price and day change from the Dhan feed; drives the header and the day stats. */
  liveQuote: LiveQuote | null = null;
  private quoteSub: Subscription | null = null;
  private themeSub?: Subscription;
  private isDarkTheme = false;
  private readonly candleCache = new Map<string, { candles: CandlestickData[]; resolvedTimeframe: ChartTimeframe; lastPrice: number; updatedAt: Date }>();
  private readonly chartSymbolMap: Record<string, { securityId: string; exchangeSegment: string; instrument: string }> = {
    NIFTY: { securityId: '13', exchangeSegment: 'IDX_I', instrument: 'INDEX' },
    BANKNIFTY: { securityId: '25', exchangeSegment: 'IDX_I', instrument: 'INDEX' },
    FINNIFTY: { securityId: '27', exchangeSegment: 'IDX_I', instrument: 'INDEX' },
    MIDCPNIFTY: { securityId: '442', exchangeSegment: 'IDX_I', instrument: 'INDEX' },
  };
  private readonly onCrosshairMove = (param: MouseEventParams<Time>) => {
    const unix = this.toUnixFromChartTime(param.time as Time);
    if (!unix || this.liveCandles.length === 0) {
      this.hoveredCandle = null;
      return;
    }

    const found = this.liveCandles.find((c) => Number(c.time) === unix) || null;
    this.hoveredCandle = found;
  };

  get activeCandle(): CandlestickData | null {
    return this.hoveredCandle ?? this.lastVisibleCandle;
  }

  get liveTransportLabel(): string {
    switch (this.liveTransportStatus) {
      case 'ws':
        return 'Live';
      case 'polling':
        return 'Polling';
      case 'closed':
        return 'Closed';
      case 'connecting':
        return 'Connecting';
      case 'idle':
      default:
        return 'Idle';
    }
  }

  get liveTransportClass(): string {
    return `transport-${this.liveTransportStatus}`;
  }

  constructor(
    private route: ActivatedRoute,
    private strategyService: StrategyService,
    private stockService: StockService,
    private announcementService: AnnouncementService,
    private marketStream: MarketStreamService,
    private themeService: ThemeService,
    private dhanLiveChartService: DhanLiveChartService,
    private portfolioService: PortfolioService,
  ) {}

  ngOnInit(): void {
    this.themeSub = this.themeService.isDarkTheme$.subscribe((isDark) => {
      this.isDarkTheme = isDark;
      requestAnimationFrame(() => this.applyChartTheme());
    });

    this.routeSub = this.route.paramMap.subscribe((params) => {
      const nextSymbol = (params.get('symbol') || '').trim().toUpperCase();
      if (!nextSymbol) {
        this.error = 'No symbol provided.';
        this.loading = false;
        return;
      }

      this.symbol = nextSymbol;
      this.watchQuote();
      this.loading = true;
      this.error = '';
      this.quote = null;
      this.indexData = null;
      this.announcements = [];
      this.performanceData = null;
      this.liveChartError = '';
      this.liveChartUpdatedAt = null;
      this.liveTransportStatus = 'idle';
      this.liveLastPrice = 0;
      this.liveCandleCount = 0;
      this.liveResolvedTimeframe = this.liveTimeframe;
      this.customFromDate = '';
      this.customToDate = '';
      this.customRangeError = '';
      this.sessionNotice = '';
      this.historyMode = false;
      this.historyLoading = false;
      this.showCustomPanel = false;
      this.quickAddQty = 1;
      this.quickAddAvgPrice = '';
      this.quickAddSaving = false;
      this.quickAddError = '';
      this.quickAddSuccess = '';
      this.marketDepthError = '';
      this.marketDepthBuy = [];
      this.marketDepthSell = [];
      this.marketDepthLimit = 20;
      this.candleCache.clear();

      this.loadQuote();
      this.reloadLiveChart();
      this.loadIndicatorCandles();
      if (!this.isIndex) {  // announcements, NSE returns and order book exist only for stocks
        this.loadAnnouncements();
        this.loadYearwiseData();
        this.loadMarketDepth(20);
      }
    });
  }

  ngAfterViewInit(): void {
    this.scheduleChartRefresh();
  }

  ngOnDestroy(): void {
    this.routeSub?.unsubscribe();
    this.quoteSub?.unsubscribe();
    this.themeSub?.unsubscribe();
    this.stopLiveUpdates();
    this.indicatorSub?.unsubscribe();
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    if (this.chartApi) {
      this.chartApi.unsubscribeCrosshairMove(this.onCrosshairMove);
      this.chartApi.remove();
      this.chartApi = null;
    }
    this.mainSeries = null;
  }

  setLiveTimeframe(tf: ChartTimeframe): void {
    if (this.liveTimeframe === tf) return;
    this.liveTimeframe = tf;
    if (tf === 'D') {
      this.dailyRange = 'MAX';
    }
    // Choosing a live timeframe leaves the static historical view.
    this.historyMode = false;
    this.sessionNotice = '';
    this.customRangeError = '';
    this.reloadLiveChart();
  }

  setChartType(type: ChartDisplayType): void {
    if (this.chartType === type) return;
    this.chartType = type;
    this.recreateMainSeries();
    this.applyCandlesToChart(this.liveCandles, this.liveResolvedTimeframe, false);
  }

  setDepthLimit(limit: 20 | 200): void {
    if (this.marketDepthLimit === limit && (this.marketDepthBuy.length || this.marketDepthSell.length)) {
      return;
    }
    this.loadMarketDepth(limit);
  }

  setDailyRange(range: '1D' | '5D' | '1M' | '3M' | '6M' | '1Y' | '2Y' | '5Y' | '10Y' | 'MAX'): void {
    if (this.dailyRange === range) return;
    this.dailyRange = range;
    this.customRangeError = '';
    this.applyDailyRangeFromCache();
  }

  toggleCustomPanel(): void {
    this.showCustomPanel = !this.showCustomPanel;
    if (this.showCustomPanel && !this.customToDate) {
      // Seed a sensible default window: last 5 days ending today (IST).
      const today = new Date();
      const from = new Date(today.getTime() - 5 * 24 * 60 * 60 * 1000);
      this.customToDate = this.toDateInputValue(today);
      this.customFromDate = this.toDateInputValue(from);
      this.customInterval = this.liveTimeframe;
    }
  }

  /**
   * Fetch a static historical window at the chosen interval. Works identically
   * whether the market is open or closed, and stops any live streaming.
   */
  applyCustomDateRange(): void {
    this.customRangeError = '';

    if (!this.customFromDate || !this.customToDate) {
      this.customRangeError = 'Pick both a From and a To date.';
      return;
    }

    if (this.customFromDate > this.customToDate) {
      this.customRangeError = 'From date must be on or before To date.';
      return;
    }

    // The backend chunks long intraday windows across Dhan's 90-day per-request
    // cap, so the only limit here is keeping the payload small enough to render.
    const spanDays = this.daysBetween(this.customFromDate, this.customToDate);
    const maxDays = this.maxRangeDays(this.customInterval);
    if (maxDays !== null && spanDays > maxDays) {
      this.customRangeError =
        `${this.intervalLabel(this.customInterval)} candles are limited to ${maxDays} days per range. `
        + 'Pick a shorter window or a larger interval.';
      return;
    }

    // Historical view is static — shut down live ticks before loading.
    this.stopLiveUpdates();
    this.historyLoading = true;
    this.liveChartLoading = true;
    this.liveChartError = '';
    this.liveTransportStatus = 'idle';

    const req: DhanChartRequest = {
      ...this.getLiveChartRequest(),
      timeframe: this.customInterval,
    };

    this.dhanLiveChartService.getHistory(req, this.customFromDate, this.customToDate).subscribe({
      next: (res) => {
        const candles = this.normalizeCandles(res.candles || []);
        this.historyMode = true;
        this.historyLoading = false;
        this.liveChartLoading = false;
        this.liveResolvedTimeframe = this.customInterval;

        if (candles.length === 0) {
          this.sessionNotice = '';
          this.customRangeError = 'No candles available for that range. Try a wider window or a different interval.';
          return;
        }

        this.applyCandlesToChart(candles, this.customInterval, true);
        this.sessionNotice = `Historical · ${this.intervalLabel(this.customInterval)} · ${res.fromDate} → ${res.toDate}`;
      },
      error: (err: HttpErrorResponse) => {
        this.historyLoading = false;
        this.liveChartLoading = false;
        this.customRangeError = err?.error?.detail || 'Unable to load that historical range right now.';
      },
    });
  }

  /** Leave historical mode and return to the smart-default live/last-session view. */
  clearCustomDateRange(): void {
    this.customFromDate = '';
    this.customToDate = '';
    this.customRangeError = '';
    this.sessionNotice = '';
    this.historyMode = false;
    this.candleCache.delete(this.getChartCacheKey(this.symbol, this.liveTimeframe));
    this.reloadLiveChart();
  }

  intervalLabel(tf: ChartTimeframe): string {
    return this.customIntervalOptions.find((o) => o.value === tf)?.label ?? tf;
  }

  /**
   * Practical span cap per interval, sized to keep the rendered series
   * manageable. Null means no limit. Dhan's own 90-day per-request cap is
   * handled server-side by chunking, so these are deliberately generous.
   */
  maxRangeDays(tf: ChartTimeframe): number | null {
    switch (tf) {
      case '1': return 30;
      case '5': return 120;
      case '15': return 365;
      case '25': return 365;
      case '60': return 730;
      case 'D': return null;
      default: return 90;
    }
  }

  get customRangeHint(): string {
    const maxDays = this.maxRangeDays(this.customInterval);
    const label = this.intervalLabel(this.customInterval);
    return maxDays === null
      ? `${label} candles: full history available.`
      : `${label} candles: up to ${maxDays} days per range. Longer windows are fetched in batches.`;
  }

  private toDateInputValue(value: Date): string {
    return value.toISOString().slice(0, 10);
  }

  private daysBetween(fromIso: string, toIso: string): number {
    const from = new Date(`${fromIso}T00:00:00Z`).getTime();
    const to = new Date(`${toIso}T00:00:00Z`).getTime();
    if (!Number.isFinite(from) || !Number.isFinite(to)) return 0;
    return Math.round((to - from) / (24 * 60 * 60 * 1000));
  }

  private normalizeCandles(raw: Array<{ time: number; open: number; high: number; low: number; close: number }>): CandlestickData[] {
    const dedup = new Map<number, CandlestickData>();
    for (const c of raw) {
      const time = Number(c.time);
      const open = Number(c.open);
      const high = Number(c.high);
      const low = Number(c.low);
      const close = Number(c.close);

      if (
        !Number.isFinite(time)
        || !Number.isFinite(open)
        || !Number.isFinite(high)
        || !Number.isFinite(low)
        || !Number.isFinite(close)
      ) {
        continue;
      }

      dedup.set(time, { time: time as UTCTimestamp, open, high, low, close });
    }

    return Array.from(dedup.values()).sort((a, b) => Number(a.time) - Number(b.time));
  }

  get isIndex(): boolean {
    return this.symbol.startsWith('INDEX:');
  }

  /** The pill text: "NIFTY" rather than the "INDEX:NIFTY" key. */
  get symbolLabel(): string {
    return this.isIndex ? this.symbol.slice('INDEX:'.length) : this.symbol;
  }

  private loadIndex(): void {
    this.stockService.getIndexAnalysis(this.symbol).subscribe({
      next: (res) => {
        const o = res.overview;
        this.indexData = res;
        // The header and chart read these quote fields; the live level comes from watchQuote.
        this.quote = {
          info: { companyName: res.name },
          last: o?.last ?? 0,
          previousClose: o?.previousClose,
          priceInfo: { previousClose: o?.previousClose, weekHighLow: { max: o?.yearHigh, min: o?.yearLow } },
          exchange: res.exchange,
          securityInfo: {},
        };
        this.loading = false;
        this.scheduleChartRefresh();
      },
      error: () => {
        this.error = 'Unable to load this index right now.';
        this.loading = false;
      },
    });
  }

  get isBseOnly(): boolean {
    return !this.isIndex && this.quote?.exchange === 'BSE';
  }

  get fullName(): string {
    return this.quote?.info?.companyName || this.quote?.metadata?.companyName || this.symbol;
  }

  get displayName(): string {
    return shortCompanyName(this.fullName);
  }

  private watchQuote(): void {
    this.quoteSub?.unsubscribe();
    this.liveQuote = null;
    const { securityId, exchangeSegment, instrument } = this.getLiveChartRequest();
    this.quoteSub = this.marketStream
      .watchQuote(this.symbol, { securityId, exchangeSegment, instrument })
      .subscribe((q) => {
        this.liveQuote = q;
        this.updateTodayCandle();
      });
  }

  /** 1D: today's candle from the live quote (the day's open/high/low and last price), so it moves while
   *  the market is open and doesn't wait for the provider's daily history. */
  private updateTodayCandle(): void {
    const q = this.liveQuote;
    if (!q || this.liveTimeframe !== 'D' || this.historyMode || !this.mainSeries || !q.open || !q.high || !q.low) return;
    const day = Math.floor((q.ts + IST_OFFSET_SECONDS) / 86400) * 86400 - IST_OFFSET_SECONDS;  // IST midnight
    const last = this.liveCandles[this.liveCandles.length - 1];
    if (!last || Number(last.time) > day) return;
    const candle: CandlestickData = {
      time: day as UTCTimestamp, open: q.open, high: Math.max(q.high, q.price), low: Math.min(q.low, q.price), close: q.price,
    };
    if (Number(last.time) === day) {
      this.liveCandles[this.liveCandles.length - 1] = candle;
    } else {
      this.liveCandles.push(candle);
    }
    this.mainSeries.update(this.toSeriesPoint(candle) as any);
    this.lastVisibleCandle = candle;
    this.liveCandleCount = this.liveCandles.length;
  }

  get lastPrice(): number {
    if (this.liveQuote) return this.liveQuote.price;
    if (Number.isFinite(this.liveLastPrice) && this.liveLastPrice > 0) {
      return Number(this.liveLastPrice);
    }

    return Number(
      this.quote?.tradeInfo?.lastPrice
      ?? this.quote?.priceInfo?.lastPrice
      ?? this.quote?.metadata?.lastPrice
      ?? this.quote?.last
      ?? 0,
    );
  }

  get prevClose(): number {
    if (this.liveQuote?.prev_close) return this.liveQuote.prev_close;
    return Number(
      this.quote?.priceInfo?.previousClose
      ?? this.quote?.previousClose
      ?? this.quote?.prev_close
      ?? 0,
    );
  }

  get priceChange(): number {
    const lp = this.lastPrice;
    const pc = this.prevClose;
    if (Number.isFinite(lp) && Number.isFinite(pc) && pc > 0) {
      return lp - pc;
    }

    const direct = Number(this.quote?.priceInfo?.change ?? this.quote?.change ?? Number.NaN);
    if (Number.isFinite(direct)) return direct;

    return 0;
  }

  get pctChange(): number {
    const pc = this.prevClose;
    if (pc > 0) {
      return (this.priceChange / pc) * 100;
    }

    const direct = Number(this.quote?.priceInfo?.pChange ?? this.quote?.percChange ?? Number.NaN);
    if (Number.isFinite(direct)) return direct;

    return 0;
  }

  get isPositive(): boolean {
    return this.priceChange >= 0;
  }

  /** NSE's classification, e.g. "Financial Services · Banks" (sector · industry). */
  get industryLabel(): string {
    const sec = this.quote?.securityInfo || {};
    return [...new Set([sec.sector, sec.industryInfo].filter(Boolean))].join(' · ');
  }

  /** The full NSE path, macro to basic industry, shown on hover. */
  get industryPath(): string {
    const sec = this.quote?.securityInfo || {};
    return [...new Set([sec.macro, sec.sector, sec.industryInfo, sec.basicIndustry].filter(Boolean))].join(' › ');
  }

  get quoteTime(): string {
    if (this.liveQuote) {
      return new Date(this.liveQuote.ts * 1000).toLocaleString('en-IN', {
        day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
        hour12: false, timeZone: 'Asia/Kolkata',
      });
    }
    return this.quote?.metadata?.lastUpdateTime || this.quote?.timestamp || '--';
  }

  get stats(): Array<{ label: string; value: string | number; raw?: number | null }> {
    const live = this.liveQuote;
    const trade = this.quote?.tradeInfo || {};
    const price = this.quote?.priceInfo || {};
    const security = this.quote?.securityInfo || {};

    return [
      { label: 'Open', value: this.formatNumber(live?.open ?? (trade.open || this.quote?.open)) },
      { label: 'High', value: this.formatNumber(live?.high ?? (trade.intraDayHighLow?.max || this.quote?.high)), raw: live?.high },
      { label: 'Low', value: this.formatNumber(live?.low ?? (trade.intraDayHighLow?.min || this.quote?.low)), raw: live?.low },
      { label: 'Prev Close', value: this.formatNumber(price.previousClose || this.quote?.previousClose) },
      { label: 'VWAP', value: this.formatNumber(trade.averagePrice) },
      { label: 'Traded Volume', value: this.formatIndianNumber(live?.volume ?? trade.totalTradedVolume), raw: live?.volume },
      { label: 'Traded Value', value: this.formatIndianNumber(trade.totalTradedValue) },
      { label: '52W High', value: this.formatNumber(price.weekHighLow?.max) },
      { label: '52W Low', value: this.formatNumber(price.weekHighLow?.min) },
      { label: 'Face Value', value: this.formatNumber(security.faceValue || trade.faceValue) },
      { label: 'P/E', value: this.formatNumber(security.pdSymbolPe || security.pdSectorPe) },
      { label: 'Industry', value: security.basicIndustry || security.industryInfo || '--' },
    ];
  }

  get performanceCards(): Array<{ label: string; stock: number; index: number }> {
    const p = this.performanceData;
    if (!p) return [];

    return [
      { label: '1W', stock: Number(p.one_week_chng_per ?? 0), index: Number(p.index_one_week_chng_per ?? 0) },
      { label: '1M', stock: Number(p.one_month_chng_per ?? 0), index: Number(p.index_one_month_chng_per ?? 0) },
      { label: 'YTD', stock: Number(p.yesterday_chng_per ?? 0), index: Number(p.index_yesterday_chng_per ?? 0) },
      { label: '1Y', stock: Number(p.one_year_chng_per ?? 0), index: Number(p.index_one_year_chng_per ?? 0) },
      { label: '3Y', stock: Number(p.three_year_chng_per ?? 0), index: Number(p.index_three_year_chng_per ?? 0) },
      { label: '5Y', stock: Number(p.five_year_chng_per ?? 0), index: Number(p.index_five_year_chng_per ?? 0) },
    ];
  }

  private loadQuote(): void {
    if (this.isIndex) {
      this.loadIndex();
      return;
    }
    this.strategyService.getSymbolData(this.symbol).subscribe({
      next: (res) => {
        this.quote = this.normalizeQuoteResponse(res);
        if (!this.quickAddAvgPrice && this.lastPrice > 0) {
          this.quickAddAvgPrice = this.lastPrice.toFixed(2);
        }
        this.loading = false;
        this.scheduleChartRefresh();
      },
      error: () => {
        this.error = 'Unable to load stock details right now.';
        this.loading = false;
      },
    });
  }

  private loadAnnouncements(): void {
    this.announcementsLoading = true;
    this.announcementService.getNSEAnnouncements(this.symbol, undefined, undefined, 8).subscribe({
      next: (res) => {
        this.announcements = Array.isArray(res?.announcements) ? res.announcements : [];
        this.announcementsLoading = false;
      },
      error: () => {
        this.announcementsLoading = false;
        this.announcements = [];
      },
    });
  }

  private loadYearwiseData(): void {
    this.performanceLoading = true;
    this.strategyService.getYearwiseData(this.symbol).subscribe({
      next: (res) => {
        const rows = Array.isArray(res?.data) ? res.data : [];
        this.performanceData = rows.length > 0 ? rows[0] : null;
        this.performanceLoading = false;
      },
      error: () => {
        this.performanceData = null;
        this.performanceLoading = false;
      },
    });
  }

  private initLiveChart(): boolean {
    const container = document.getElementById('stockDetailChart') as HTMLDivElement | null;
    if (!container) return false;

    if (this.chartApi) {
      this.chartApi.unsubscribeCrosshairMove(this.onCrosshairMove);
      this.chartApi.remove();
      this.chartApi = null;
      this.mainSeries = null;
    }
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;

    const dark = this.isDarkModeFromDom();
    const cardBg = this.getThemeColor('--card', dark ? '#0b1020' : '#ffffff');
    const fg = this.getThemeColor('--foreground', dark ? '#cbd5e1' : '#334155');
    const border = this.getThemeColor('--border', dark ? 'rgba(255, 255, 255, 0.18)' : 'rgba(148, 163, 184, 0.35)');

    this.chartApi = createChart(container, {
      width: Math.max(320, container.clientWidth),
      height: 360,
      layout: {
        textColor: fg,
        background: { type: ColorType.Solid, color: cardBg },
      },
      localization: {
        locale: 'en-IN',
        timeFormatter: (time: Time) => this.formatIstTime(time),
      },
      grid: {
        vertLines: { color: dark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(148, 163, 184, 0.22)' },
        horzLines: { color: dark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(148, 163, 184, 0.22)' },
      },
      rightPriceScale: {
        borderColor: border,
      },
      timeScale: {
        borderColor: border,
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: Time) => this.formatIstTime(time),
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: true,
      },
    });

    this.recreateMainSeries();

    this.resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry || !this.chartApi) return;
      const width = Math.max(320, Math.floor(entry.contentRect.width));
      this.chartApi.applyOptions({ width });
      this.chartApi.timeScale().fitContent();
    });
    this.resizeObserver.observe(container);
    this.chartApi.subscribeCrosshairMove(this.onCrosshairMove);

    return true;
  }

  private applyChartTheme(): void {
    if (!this.chartApi) return;

    const dark = this.isDarkModeFromDom();
    const cardBg = this.getThemeColor('--card', dark ? '#0b1020' : '#ffffff');
    const fg = this.getThemeColor('--foreground', dark ? '#cbd5e1' : '#334155');
    const border = this.getThemeColor('--border', dark ? 'rgba(255, 255, 255, 0.18)' : 'rgba(148, 163, 184, 0.35)');

    this.chartApi.applyOptions({
      layout: {
        textColor: fg,
        background: { type: ColorType.Solid, color: cardBg },
      },
      grid: {
        vertLines: { color: dark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(148, 163, 184, 0.22)' },
        horzLines: { color: dark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(148, 163, 184, 0.22)' },
      },
      rightPriceScale: {
        borderColor: border,
      },
      timeScale: {
        borderColor: border,
      },
    });
  }

  private getThemeColor(cssVar: string, fallback: string): string {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(cssVar).trim();
    if (!raw) return fallback;
    return `hsl(${raw})`;
  }

  private isDarkModeFromDom(): boolean {
    return document.documentElement.classList.contains('dark');
  }

  private scheduleChartRefresh(attempt = 0): void {
    // The chart host is inside an @if block and may appear after async data resolves.
    const initialized = this.initLiveChart();
    if (initialized) {
      this.reloadLiveChart();
      return;
    }

    if (attempt >= 20) {
      this.liveChartError = 'Live chart container did not initialize in time.';
      return;
    }

    setTimeout(() => this.scheduleChartRefresh(attempt + 1), 50);
  }

  private getLiveChartRequest(): DhanChartRequest {
    const mapping = this.chartSymbolMap[this.symbol];

    return {
      symbol: this.symbol,
      timeframe: this.liveTimeframe,
      securityId: mapping?.securityId,
      exchangeSegment: mapping?.exchangeSegment,
      instrument: mapping?.instrument,
    };
  }

  private getChartCacheKey(symbol: string, timeframe: ChartTimeframe): string {
    return `${symbol}:${timeframe}`;
  }

  private toLineData(candles: CandlestickData[]): Array<LineData<UTCTimestamp>> {
    return candles.map((c) => ({ time: c.time as UTCTimestamp, value: Number(c.close) }));
  }

  private toBarData(candles: CandlestickData[]): Array<BarData<UTCTimestamp>> {
    return candles.map((c) => ({
      time: c.time as UTCTimestamp,
      open: Number(c.open),
      high: Number(c.high),
      low: Number(c.low),
      close: Number(c.close),
    }));
  }

  private recreateMainSeries(): void {
    if (!this.chartApi) return;
    if (this.mainSeries) {
      this.chartApi.removeSeries(this.mainSeries);
      this.mainSeries = null;
    }

    switch (this.chartType) {
      case 'line':
        this.mainSeries = this.chartApi.addSeries(LineSeries, {
          color: '#0ea5e9',
          lineWidth: 2,
        });
        break;
      case 'bar':
        this.mainSeries = this.chartApi.addSeries(BarSeries, {
          upColor: '#16a34a',
          downColor: '#dc2626',
        });
        break;
      case 'area':
        this.mainSeries = this.chartApi.addSeries(AreaSeries, {
          lineColor: '#0284c7',
          topColor: 'rgba(2, 132, 199, 0.25)',
          bottomColor: 'rgba(2, 132, 199, 0.02)',
        });
        break;
      case 'baseline':
        this.mainSeries = this.chartApi.addSeries(BaselineSeries, {
          topLineColor: '#16a34a',
          topFillColor1: 'rgba(22, 163, 74, 0.18)',
          topFillColor2: 'rgba(22, 163, 74, 0.04)',
          bottomLineColor: '#dc2626',
          bottomFillColor1: 'rgba(220, 38, 38, 0.18)',
          bottomFillColor2: 'rgba(220, 38, 38, 0.04)',
          baseValue: { type: 'price', price: this.liveLastPrice || this.lastPrice || 0 },
        });
        break;
      case 'candlestick':
      default:
        this.mainSeries = this.chartApi.addSeries(CandlestickSeries, {
          upColor: '#16a34a',
          downColor: '#dc2626',
          borderVisible: false,
          wickUpColor: '#16a34a',
          wickDownColor: '#dc2626',
        });
        break;
    }
  }

  /** Trend and momentum from daily closes, the same maths as the screener. */
  get technicals(): Technicals | null {
    const closes = this.getIndicatorSourceCandles().map((c) => Number(c.close));
    if (closes.length < 2) return null;
    const close = closes[closes.length - 1];
    const raw = [50, 100, 200].map((days) => {
      const value = movingAverage(closes, days);
      return { days, value, gapPct: value ? ((close - value) / value) * 100 : null };
    });
    const widest = Math.max(1, ...raw.map((a) => Math.abs(a.gapPct ?? 0)));
    const averages = raw.map((a) => ({ ...a, barPct: a.gapPct == null ? 0 : (Math.abs(a.gapPct) / widest) * 50 }));
    const signal = trendSignal(close, raw[0].value, raw[1].value, raw[2].value);
    const mom = momentum(closes, 10);
    return {
      signal,
      summary: this.trendSummary(signal, raw),
      averages,
      momentum: mom,
      momentumPct: mom == null ? null : (mom / (close - mom)) * 100,
      sparkPath: this.sparkPath(closes.slice(-11)),
    };
  }

  private trendSummary(signal: TrendSignal, averages: Array<{ days: number; gapPct: number | null }>): string {
    if (signal === 'Bullish') return 'Price is above its 50, 100 and 200-day averages, and they are stacked upward: a clear uptrend.';
    if (signal === 'Bearish') return 'Price is below its 50, 100 and 200-day averages, and they are stacked downward: a clear downtrend.';
    if (signal === 'N/A') return 'Fewer than 200 sessions of history, so the full trend check is not available yet.';
    const days = (list: number[]) => list.join(' and ');
    const above = averages.filter((a) => (a.gapPct ?? 0) >= 0).map((a) => a.days);
    const below = averages.filter((a) => (a.gapPct ?? 0) < 0).map((a) => a.days);
    if (!below.length) return 'Price is above all three averages, but they are not stacked in order yet, so the uptrend is not confirmed.';
    if (!above.length) return 'Price is below all three averages, but they are not stacked in order yet, so the downtrend is not confirmed.';
    return `Price is above its ${days(above)}-day and below its ${days(below)}-day average, so there is no clear trend.`;
  }

  /** SVG path for the last few closes in a 100 x 30 box. */
  private sparkPath(closes: number[]): string {
    const lo = Math.min(...closes);
    const span = Math.max(...closes) - lo || 1;
    return closes
      .map((c, i) => `${i ? 'L' : 'M'}${((i / (closes.length - 1)) * 100).toFixed(1)},${(28 - ((c - lo) / span) * 26).toFixed(1)}`)
      .join(' ');
  }

  /** Daily candles for the indicators, shared with the 1D chart through the candle cache. */
  private loadIndicatorCandles(): void {
    const symbol = this.symbol;
    const cacheKey = this.getChartCacheKey(symbol, 'D');
    this.indicatorSub?.unsubscribe();
    this.indicatorsError = false;
    if (this.candleCache.get(cacheKey)?.candles.length) return;
    this.indicatorsLoading = true;
    this.indicatorSub = this.dhanLiveChartService.getBootstrap({ ...this.getLiveChartRequest(), timeframe: 'D' }).subscribe({
      next: (res) => {
        if (symbol !== this.symbol) return;
        const candles = this.normalizeCandles(res.candles || []);
        this.candleCache.set(cacheKey, {
          candles,
          resolvedTimeframe: 'D',
          lastPrice: candles.length > 0 ? candles[candles.length - 1].close : 0,
          updatedAt: new Date(),
        });
        this.indicatorsLoading = false;
      },
      error: () => {
        this.indicatorsLoading = false;
        this.indicatorsError = symbol === this.symbol;
      },
    });
  }

  /** Daily closes only (never intraday bars); today's bar closes at the live price. */
  private getIndicatorSourceCandles(): CandlestickData[] {
    const daily = this.candleCache.get(this.getChartCacheKey(this.symbol, 'D'))?.candles ?? [];
    if (!daily.length) return [];
    const last = daily[daily.length - 1];
    const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
    const lastDay = new Date(Number(last.time) * 1000).toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
    // Today's daily bar closes at the live price, so the averages and momentum move with the market.
    if (this.liveQuote && lastDay === today) {
      return [...daily.slice(0, -1), { ...last, close: this.liveQuote.price }];
    }
    return daily;
  }

  private applyCandlesToChart(candles: CandlestickData[], resolved: ChartTimeframe, fit = true): void {
    this.liveCandles = candles;
    if (this.mainSeries) {
      if (this.chartType === 'candlestick') {
        this.mainSeries.setData(candles as any);
      } else if (this.chartType === 'bar') {
        this.mainSeries.setData(this.toBarData(candles) as any);
      } else {
        this.mainSeries.setData(this.toLineData(candles) as any);
      }
    }
    this.lastVisibleCandle = candles.length > 0 ? candles[candles.length - 1] : null;
    if (this.hoveredCandle) {
      const hoveredUnix = Number(this.hoveredCandle.time);
      this.hoveredCandle = candles.find((c) => Number(c.time) === hoveredUnix) || null;
    }
    if (!this.hoveredCandle) {
      this.hoveredCandle = this.lastVisibleCandle;
    }
    this.liveCandleCount = candles.length;
    this.liveResolvedTimeframe = resolved;
    if (candles.length > 0) {
      this.liveLastPrice = candles[candles.length - 1].close;
    }
    if (fit) {
      this.chartApi?.timeScale().fitContent();
    }
    this.liveChartUpdatedAt = new Date();
    if (resolved === 'D') this.updateTodayCandle();
  }

  private loadMarketDepth(limit: 20 | 200): void {
    this.marketDepthLoading = true;
    this.marketDepthError = '';
    this.marketDepthLimit = limit;

    const req = this.getLiveChartRequest();
    this.dhanLiveChartService.getMarketDepth(req, limit).subscribe({
      next: (res) => {
        this.marketDepthBuy = Array.isArray(res.buy) ? res.buy : [];
        this.marketDepthSell = Array.isArray(res.sell) ? res.sell : [];
        this.marketDepthNote = depthNote(res);
        this.marketDepthLoading = false;
      },
      error: (err: HttpErrorResponse) => {
        this.marketDepthLoading = false;
        this.marketDepthError = err?.error?.detail || 'Market depth is unavailable right now.';
      },
    });
  }

  private getRangeDays(range: '1D' | '5D' | '1M' | '3M' | '6M' | '1Y' | '2Y' | '5Y' | '10Y' | 'MAX'): number | null {
    switch (range) {
      case '1D': return 1;
      case '5D': return 5;
      case '1M': return 30;
      case '3M': return 90;
      case '6M': return 180;
      case '1Y': return 365;
      case '2Y': return 730;
      case '5Y': return 1825;
      case '10Y': return 3650;
      case 'MAX':
      default:
        return null;
    }
  }

  private filterDailyCandles(candles: CandlestickData[]): CandlestickData[] {
    if (candles.length === 0) {
      return candles;
    }

    if (this.customFromDate && this.customToDate) {
      const fromStart = new Date(`${this.customFromDate}T00:00:00+05:30`).getTime() / 1000;
      const toEnd = new Date(`${this.customToDate}T23:59:59+05:30`).getTime() / 1000;
      const customFiltered = candles.filter((c) => {
        const t = Number(c.time);
        return t >= fromStart && t <= toEnd;
      });
      if (customFiltered.length > 0) {
        return customFiltered;
      }
      return candles;
    }

    if (this.dailyRange === 'MAX') {
      return candles;
    }

    const days = this.getRangeDays(this.dailyRange);
    if (!days) return candles;

    const last = Number(candles[candles.length - 1].time);
    const cutoff = last - (days * 24 * 60 * 60);
    const filtered = candles.filter((c) => Number(c.time) >= cutoff);
    return filtered.length > 0 ? filtered : candles;
  }

  private applyDailyRangeFromCache(): void {
    if (this.liveTimeframe !== 'D') return;
    const cacheKey = this.getChartCacheKey(this.symbol, 'D');
    const cached = this.candleCache.get(cacheKey);
    if (!cached || cached.candles.length === 0) return;

    const filtered = this.filterDailyCandles(cached.candles);
    this.applyCandlesToChart(filtered, 'D');
  }

  private reloadLiveChart(): void {
    if (!this.symbol || !this.mainSeries) return;

    this.stopLiveUpdates();
    this.liveChartError = '';
    if (this.liveTimeframe !== 'D') {
      this.watchLive();
      return;
    }

    // Daily candles come from REST history; intraday is streamed (watchLive).
    this.liveChartLoading = true;
    this.liveTransportStatus = 'idle';
    const cacheKey = this.getChartCacheKey(this.symbol, 'D');
    const cached = this.candleCache.get(cacheKey);
    if (cached && cached.candles.length > 0) {
      this.applyCandlesToChart(this.filterDailyCandles(cached.candles), 'D', true);
      this.liveChartLoading = false;
      return;
    }

    this.chartLoadSub = this.dhanLiveChartService.getBootstrap(this.getLiveChartRequest()).subscribe({
      next: (res) => {
        const candles = this.normalizeCandles(res.candles || []);
        this.candleCache.set(cacheKey, {
          candles,
          resolvedTimeframe: 'D',
          lastPrice: candles.length > 0 ? candles[candles.length - 1].close : 0,
          updatedAt: new Date(),
        });
        this.applyCandlesToChart(this.filterDailyCandles(candles), 'D', true);
        this.liveChartLoading = false;
      },
      error: (err: HttpErrorResponse) => {
        this.liveChartLoading = false;
        this.liveChartError = this.resolveChartErrorMessage(err);
      },
    });
  }

  /** Intraday: a snapshot of about a week of candles, then live deltas (backend/market/service.py). */
  private watchLive(): void {
    this.liveChartLoading = true;
    this.liveTransportStatus = 'connecting';
    const req = this.getLiveChartRequest();
    this.liveSub = this.marketStream
      .watch({
        symbol: req.symbol,
        tf: this.liveTimeframe as MarketStreamRequest['tf'],
        securityId: req.securityId,
        exchangeSegment: req.exchangeSegment,
        instrument: req.instrument,
      })
      .subscribe((msg) => this.onStreamMessage(msg));
  }

  private onStreamMessage(msg: MarketStreamMessage): void {
    if (msg.op === 'error') {
      this.liveChartLoading = false;
      this.liveTransportStatus = 'idle';
      this.liveChartError = msg.detail;
      return;
    }
    if (msg.op === 'snapshot') {
      if (msg.history === 'pending') {
        // The provider's intraday history hasn't loaded yet (it is often down before the open). Stay on
        // this timeframe: live candles arrive as deltas, and a full snapshot follows once history loads.
        this.applyCandlesToChart(msg.candles.map(toCandle), this.liveTimeframe, false);
        this.showRecentBars();
        this.liveChartLoading = false;
        this.liveTransportStatus = msg.market === 'open' ? 'ws' : 'closed';
        this.sessionNotice = 'Intraday history is loading · live candles appear as trades happen';
        return;
      }
      if (msg.candles.length === 0) {
        // Thinly traded stocks can go a week without a trade; daily candles still show their history.
        this.setLiveTimeframe('D');
        this.sessionNotice = 'No trades in the last week, so this shows daily candles';
        return;
      }
      this.applyCandlesToChart(msg.candles.map(toCandle), this.liveTimeframe, false);
      this.showRecentBars();
      this.liveChartLoading = false;
      if (msg.source === 'rest') {
        this.liveTransportStatus = 'polling';
        this.sessionNotice = 'Live feed unavailable · refreshing every minute';
      } else {
        this.liveTransportStatus = msg.market === 'open' ? 'ws' : 'closed';
        this.sessionNotice = msg.market === 'open' ? '' : 'Market closed · showing the latest sessions';
      }
      if (msg.last) this.liveChartUpdatedAt = new Date(msg.last.ts * 1000);
      return;
    }

    // A delta only touches the forming bar: update it in place instead of redrawing the series.
    const candle = toCandle(msg.candle);
    const last = this.liveCandles[this.liveCandles.length - 1];
    if (last && Number(last.time) > Number(candle.time)) return;
    if (last && Number(last.time) === Number(candle.time)) {
      this.liveCandles[this.liveCandles.length - 1] = candle;
    } else {
      this.liveCandles.push(candle);
    }
    this.mainSeries?.update(this.toSeriesPoint(candle) as any);
    this.lastVisibleCandle = candle;
    this.liveCandleCount = this.liveCandles.length;
    this.liveLastPrice = Number(candle.close);
    this.liveChartUpdatedAt = new Date(msg.last.ts * 1000);
    this.liveTransportStatus = 'ws';
  }

  /** Open on the latest ~120 bars rather than squeezing a week of history into view. */
  private showRecentBars(): void {
    const n = this.liveCandles.length;
    if (n > 0) this.chartApi?.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 120), to: n + 2 });
  }

  private toSeriesPoint(c: CandlestickData): CandlestickData | BarData<UTCTimestamp> | LineData<UTCTimestamp> {
    if (this.chartType === 'candlestick' || this.chartType === 'bar') {
      return { time: c.time as UTCTimestamp, open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close) };
    }
    return { time: c.time as UTCTimestamp, value: Number(c.close) };
  }

  private stopLiveUpdates(): void {
    this.liveSub?.unsubscribe();
    this.liveSub = null;
    this.chartLoadSub?.unsubscribe();
    this.chartLoadSub = null;
  }

  private toUnixFromChartTime(time: Time): number {
    if (typeof time === 'number') {
      return Number(time);
    }

    if (typeof time === 'string') {
      const parsed = Date.parse(time);
      return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : 0;
    }

    const year = Number((time as { year: number }).year);
    const month = Number((time as { month: number }).month);
    const day = Number((time as { day: number }).day);
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
      return 0;
    }

    return Math.floor(Date.UTC(year, month - 1, day) / 1000);
  }

  private formatIstTime(time: Time): string {
    const unix = this.toUnixFromChartTime(time);
    if (!unix) return '';

    if (this.liveResolvedTimeframe === 'D') {
      return new Date(unix * 1000).toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: '2-digit',
        timeZone: 'Asia/Kolkata',
      });
    }

    return new Date(unix * 1000).toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: 'Asia/Kolkata',
    });
  }

  private formatNumber(value: unknown): string {
    const n = Number(value);
    if (!Number.isFinite(n)) return '--';
    return n.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }

  private formatIndianNumber(value: unknown): string {
    const n = Number(value);
    if (!Number.isFinite(n)) return '--';
    return n.toLocaleString('en-IN');
  }


  private resolveChartErrorMessage(err: HttpErrorResponse): string {
    const detail = err?.error?.detail;
    if (err?.status >= 500) return 'Live chart unavailable right now. Please try again shortly.';
    if (typeof detail === 'string' && detail.length > 0) {
      if (detail.includes('Security ID is required')) {
        return 'Live chart unavailable: market data mapping is missing for this stock symbol.';
      }
      return `Live chart unavailable: ${detail}`;
    }
    return 'Live chart unavailable for this symbol right now.';
  }

  private normalizeQuoteResponse(raw: any): any {
    if (!raw || typeof raw !== 'object') return raw;

    const first = Array.isArray(raw?.equityResponse) && raw.equityResponse.length > 0
      ? raw.equityResponse[0]
      : null;

    if (!first || typeof first !== 'object') {
      return raw;
    }

    const meta = first.metaData || {};
    const sec = first.secInfo || {};
    const trade = first.tradeInfo || {};
    const price = first.priceInfo || {};
    const orderBook = first.orderBook || {};

    return {
      info: {
        companyName: meta.companyName || sec.issueDesc || this.symbol,
      },
      metadata: {
        ...meta,
        industry: sec.basicIndustry || sec.industryInfo,
        lastUpdateTime: first.lastUpdateTime,
      },
      securityInfo: {
        ...sec,
        faceValue: trade.faceValue,
      },
      tradeInfo: trade,
      priceInfo: {
        ...price,
        previousClose: meta.previousClose ?? price.previousClose,
        change: meta.change ?? price.change,
        pChange: meta.pChange ?? price.pChange,
        weekHighLow: {
          max: price.yearHigh ?? price.weekHighLow?.max,
          min: price.yearLow ?? price.weekHighLow?.min,
        },
      },
      orderBook,
      last: orderBook.lastPrice ?? trade.lastPrice ?? meta.closePrice ?? 0,
      open: meta.open ?? trade.open,
      high: meta.dayHigh ?? trade.intraDayHighLow?.max,
      low: meta.dayLow ?? trade.intraDayHighLow?.min,
      previousClose: meta.previousClose ?? price.previousClose,
      timestamp: first.lastUpdateTime,
      exchange: first.exchange ?? 'NSE',  // 'BSE' for BSE-only companies (quote from Dhan)
    };
  }

  addToPortfolio(): void {
    const qty = Math.max(1, Number(this.quickAddQty || 0));
    const avgPrice = Number(this.quickAddAvgPrice || 0);

    if (!this.symbol || !Number.isFinite(avgPrice) || avgPrice <= 0) {
      this.quickAddError = 'Enter a valid quantity and average price.';
      this.quickAddSuccess = '';
      return;
    }

    this.quickAddSaving = true;
    this.quickAddError = '';
    this.quickAddSuccess = '';

    this.portfolioService.addHolding({
      symbol: this.symbol,
      instrument_type: 'EQUITY',
      qty,
      avg_price: avgPrice,
    }).subscribe({
      next: () => {
        this.quickAddSaving = false;
        this.quickAddSuccess = `${this.symbol} added to portfolio.`;
      },
      error: (err) => {
        this.quickAddSaving = false;
        this.quickAddError = err?.error?.detail || 'Unable to add holding right now.';
      },
    });
  }
}
