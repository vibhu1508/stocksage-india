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
import { AnnouncementService, NSEAnnouncement } from '../../core/services/announcement.service';
import { MarketService } from '../../core/services/market.service';
import { ThemeService } from '../../core/services/theme.service';
import { PortfolioService } from '../../core/services/portfolio.service';
import {
  ChartTimeframe,
  DhanChartRequest,
  DhanChartTickResponse,
  DhanDepthLevel,
  DhanLiveChartService,
} from '../../core/services/dhan-live-chart.service';

type ChartDisplayType = 'candlestick' | 'line' | 'bar' | 'area' | 'baseline';

@Component({
  selector: 'app-stock-detail',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, LucideAngularModule],
  templateUrl: './stock-detail.component.html',
  styleUrl: './stock-detail.component.scss',
})
export class StockDetailComponent implements OnInit, AfterViewInit, OnDestroy {
  symbol = '';
  loading = true;
  error = '';

  quote: any = null;
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
  quickAddQty = 1;
  quickAddAvgPrice = '';
  quickAddSaving = false;
  quickAddError = '';
  quickAddSuccess = '';
  marketDepthLoading = false;
  marketDepthError = '';
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
  private tickTimer: ReturnType<typeof setInterval> | null = null;
  private tickStreamSub: Subscription | null = null;
  private tickFailureCount = 0;
  private themeSub?: Subscription;
  private isDarkTheme = false;
  private readonly candleCache = new Map<string, { candles: CandlestickData[]; resolvedTimeframe: ChartTimeframe; lastPrice: number; updatedAt: Date }>();
  private lastSessionStatusAt = 0;
  private lastSessionIsOpen: boolean | null = null;
  private readonly sessionStatusTtlMs = 60_000;
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
    private announcementService: AnnouncementService,
    private marketService: MarketService,
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
      this.loading = true;
      this.error = '';
      this.quote = null;
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
      this.loadAnnouncements();
      this.loadYearwiseData();
      this.reloadLiveChart();
      this.loadMarketDepth(20);
    });
  }

  ngAfterViewInit(): void {
    this.scheduleChartRefresh();
  }

  ngOnDestroy(): void {
    this.routeSub?.unsubscribe();
    this.themeSub?.unsubscribe();
    this.stopTickTimer();
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

  applyCustomDateRange(): void {
    this.customRangeError = '';

    if (!this.customFromDate || !this.customToDate) {
      this.applyDailyRangeFromCache();
      return;
    }

    if (this.customFromDate > this.customToDate) {
      this.customRangeError = 'From date must be earlier than To date.';
      return;
    }

    this.applyDailyRangeFromCache();
  }

  clearCustomDateRange(): void {
    this.customFromDate = '';
    this.customToDate = '';
    this.customRangeError = '';
    this.applyDailyRangeFromCache();
  }

  get displayName(): string {
    return this.quote?.info?.companyName || this.quote?.metadata?.companyName || this.symbol;
  }

  get lastPrice(): number {
    return Number(
      this.quote?.tradeInfo?.lastPrice
      ?? this.quote?.priceInfo?.lastPrice
      ?? this.quote?.metadata?.lastPrice
      ?? this.quote?.last
      ?? 0,
    );
  }

  get prevClose(): number {
    return Number(
      this.quote?.priceInfo?.previousClose
      ?? this.quote?.previousClose
      ?? this.quote?.prev_close
      ?? 0,
    );
  }

  get priceChange(): number {
    const direct = Number(this.quote?.priceInfo?.change ?? this.quote?.change ?? Number.NaN);
    if (Number.isFinite(direct)) return direct;

    const lp = this.lastPrice;
    const pc = this.prevClose;
    if (Number.isFinite(lp) && Number.isFinite(pc) && pc > 0) {
      return lp - pc;
    }
    return 0;
  }

  get pctChange(): number {
    const direct = Number(this.quote?.priceInfo?.pChange ?? this.quote?.percChange ?? Number.NaN);
    if (Number.isFinite(direct)) return direct;

    const pc = this.prevClose;
    if (pc > 0) {
      return (this.priceChange / pc) * 100;
    }
    return 0;
  }

  get isPositive(): boolean {
    return this.priceChange >= 0;
  }

  get quoteTime(): string {
    return this.quote?.metadata?.lastUpdateTime || this.quote?.timestamp || '--';
  }

  get stats(): Array<{ label: string; value: string | number }> {
    const trade = this.quote?.tradeInfo || {};
    const price = this.quote?.priceInfo || {};
    const security = this.quote?.securityInfo || {};
    const candles = this.getIndicatorSourceCandles();
    const ma50 = this.calculateLastMAValue(candles, 50);
    const ma100 = this.calculateLastMAValue(candles, 100);
    const ma200 = this.calculateLastMAValue(candles, 200);
    const momentum10 = this.calculateLastMomentumValue(candles, 10);

    return [
      { label: 'Open', value: this.formatNumber(trade.open || this.quote?.open) },
      { label: 'High', value: this.formatNumber(trade.intraDayHighLow?.max || this.quote?.high) },
      { label: 'Low', value: this.formatNumber(trade.intraDayHighLow?.min || this.quote?.low) },
      { label: 'Prev Close', value: this.formatNumber(price.previousClose || this.quote?.previousClose) },
      { label: 'VWAP', value: this.formatNumber(trade.averagePrice) },
      { label: 'Traded Volume', value: this.formatIndianNumber(trade.totalTradedVolume) },
      { label: 'Traded Value', value: this.formatIndianNumber(trade.totalTradedValue) },
      { label: '52W High', value: this.formatNumber(price.weekHighLow?.max) },
      { label: '52W Low', value: this.formatNumber(price.weekHighLow?.min) },
      { label: 'MA 50', value: this.formatNumber(ma50) },
      { label: 'MA 100', value: this.formatNumber(ma100) },
      { label: 'MA 200', value: this.formatNumber(ma200) },
      { label: 'Momentum (10)', value: this.formatSignedNumber(momentum10) },
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

  private getIndicatorSourceCandles(): CandlestickData[] {
    const dailyCache = this.candleCache.get(this.getChartCacheKey(this.symbol, 'D'));
    if (dailyCache && Array.isArray(dailyCache.candles) && dailyCache.candles.length > 0) {
      return dailyCache.candles;
    }
    return this.liveCandles;
  }

  private calculateLastMAValue(candles: CandlestickData[], length: number): number | null {
    if (!Array.isArray(candles) || candles.length < length) return null;
    let sum = 0;
    for (let i = candles.length - length; i < candles.length; i++) {
      const close = Number(candles[i].close);
      if (!Number.isFinite(close)) return null;
      sum += close;
    }
    return sum / length;
  }

  private calculateLastMomentumValue(candles: CandlestickData[], length: number): number | null {
    if (!Array.isArray(candles) || candles.length <= length) return null;
    const latest = Number(candles[candles.length - 1].close);
    const previous = Number(candles[candles.length - 1 - length].close);
    if (!Number.isFinite(latest) || !Number.isFinite(previous)) return null;
    return latest - previous;
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
  }

  private mergeTickIntoCandles(candles: CandlestickData[], tick: DhanChartTickResponse): CandlestickData[] {
    const intervalMinutes = Number(this.liveResolvedTimeframe || this.liveTimeframe);
    if (!Number.isFinite(intervalMinutes) || intervalMinutes <= 0) {
      return candles;
    }

    const bucketSize = intervalMinutes * 60;
    const bucketStart = Math.floor(Number(tick.timestamp) / bucketSize) * bucketSize;
    const price = Number(tick.price);
    if (!Number.isFinite(price) || price <= 0) {
      return candles;
    }

    const next = [...candles];
    const last = next[next.length - 1];
    if (last && Number(last.time) === bucketStart) {
      next[next.length - 1] = {
        time: bucketStart as UTCTimestamp,
        open: Number(last.open),
        high: Math.max(Number(last.high), price),
        low: Math.min(Number(last.low), price),
        close: price,
      };
      return next;
    }

    next.push({
      time: bucketStart as UTCTimestamp,
      open: price,
      high: price,
      low: price,
      close: price,
    });
    return next;
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

    this.stopTickTimer();
    this.tickFailureCount = 0;
    this.liveChartLoading = true;
    this.liveChartError = '';
    this.liveTransportStatus = this.liveTimeframe === 'D' ? 'idle' : 'connecting';

    const cacheKey = this.getChartCacheKey(this.symbol, this.liveTimeframe);
    const cached = this.candleCache.get(cacheKey);
    if (cached && cached.candles.length > 0) {
      const visibleCandles = cached.resolvedTimeframe === 'D' ? this.filterDailyCandles(cached.candles) : cached.candles;
      this.applyCandlesToChart(visibleCandles, cached.resolvedTimeframe, true);
      this.liveChartLoading = false;
      this.liveTransportStatus = cached.resolvedTimeframe === 'D' ? 'idle' : 'connecting';
      this.startTickTimer(2000);
      return;
    }

    this.dhanLiveChartService.getBootstrap(this.getLiveChartRequest()).subscribe({
      next: (res) => {
        const dedup = new Map<number, CandlestickData>();
        for (const c of res.candles || []) {
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

          dedup.set(time, {
            time: time as UTCTimestamp,
            open,
            high,
            low,
            close,
          });
        }

        const candles = Array.from(dedup.values()).sort((a, b) => Number(a.time) - Number(b.time));

        const resolved = String(res?.resolvedTimeframe || this.liveTimeframe) as ChartTimeframe;
        const safeResolved = ['1', '5', '15', '60', 'D'].includes(resolved) ? resolved : this.liveTimeframe;

        this.candleCache.set(cacheKey, {
          candles,
          resolvedTimeframe: safeResolved,
          lastPrice: candles.length > 0 ? candles[candles.length - 1].close : 0,
          updatedAt: new Date(),
        });

        const visibleCandles = safeResolved === 'D' ? this.filterDailyCandles(candles) : candles;
        this.applyCandlesToChart(visibleCandles, safeResolved, true);
        this.liveChartLoading = false;
        if (safeResolved === 'D') {
          this.liveChartError = '';
          this.liveTransportStatus = 'idle';
          return;
        }
        this.startTickTimer(2000);
      },
      error: (err: HttpErrorResponse) => {
        this.liveChartLoading = false;
        this.liveChartError = this.resolveChartErrorMessage(err);
        this.liveTransportStatus = 'idle';
      },
    });
  }

  private startTickTimer(intervalMs: number): void {
    this.stopTickTimer();

    if (this.liveResolvedTimeframe === 'D') {
      this.liveTransportStatus = 'idle';
      return;
    }

    const now = Date.now();
    if (this.lastSessionIsOpen !== null && (now - this.lastSessionStatusAt) < this.sessionStatusTtlMs) {
      if (!this.lastSessionIsOpen) {
        this.liveChartError = 'Market is closed. Live updates will resume on the next trading session.';
        this.liveTransportStatus = 'closed';
        return;
      }
      this.startTickStream(intervalMs);
      return;
    }

    this.marketService.getSessionStatus().subscribe({
      next: (session) => {
        this.lastSessionIsOpen = !!session?.is_open;
        this.lastSessionStatusAt = Date.now();

        if (!this.lastSessionIsOpen) {
          this.liveChartError = 'Market is closed. Live updates will resume on the next trading session.';
          this.liveTransportStatus = 'closed';
          return;
        }

        this.startTickStream(intervalMs);
      },
      error: () => {
        this.liveChartError = 'Live updates are unavailable right now.';
        this.liveTransportStatus = 'polling';
      },
    });
  }

  private startTickStream(fallbackIntervalMs: number): void {
    const tickReq: DhanChartRequest = {
      ...this.getLiveChartRequest(),
      timeframe: this.liveResolvedTimeframe,
    };

    this.tickStreamSub?.unsubscribe();
    this.liveTransportStatus = 'connecting';
    this.tickStreamSub = this.dhanLiveChartService.streamTicks(tickReq).subscribe({
      next: (tick) => {
        this.tickFailureCount = 0;
        this.liveChartError = '';
        this.liveTransportStatus = 'ws';
        this.applyTick(tick);
      },
      error: () => {
        this.liveChartError = 'Live stream disconnected, falling back to polling.';
        this.liveTransportStatus = 'polling';
        this.startTickInterval(Math.max(2000, fallbackIntervalMs));
      },
      complete: () => {
        if (!this.tickTimer) {
          this.startTickInterval(Math.max(2000, fallbackIntervalMs));
        }
      },
    });
  }

  private startTickInterval(intervalMs: number): void {
    this.liveTransportStatus = 'polling';
    this.tickTimer = setInterval(() => {
          if (!this.isMarketOpenNow()) {
            this.stopTickTimer();
            this.liveChartError = 'Market is closed. Live updates will resume on the next trading session.';
            this.liveTransportStatus = 'closed';
            return;
          }

          const tickReq: DhanChartRequest = {
            ...this.getLiveChartRequest(),
            timeframe: this.liveResolvedTimeframe,
          };

          this.dhanLiveChartService.getLatestTick(tickReq).subscribe({
            next: (tick) => {
              this.tickFailureCount = 0;
              this.liveChartError = '';
              this.liveTransportStatus = 'polling';
              this.applyTick(tick);
            },
            error: (_err: HttpErrorResponse) => {
              this.tickFailureCount += 1;
              // Avoid noisy transient provider errors in UI; only show a soft delay signal.
              if (this.tickFailureCount >= 3) {
                this.liveChartError = 'Live updates delayed, showing last known chart data.';
              }

              if (this.tickFailureCount >= 6) {
                this.stopTickTimer();
                setTimeout(() => this.reloadLiveChart(), 15000);
                return;
              }

              if (this.tickFailureCount >= 3) {
                this.startTickTimer(5000);
              }
            },
          });
        }, intervalMs);
  }

  private stopTickTimer(): void {
    this.tickStreamSub?.unsubscribe();
    this.tickStreamSub = null;

    if (!this.tickTimer) return;
    clearInterval(this.tickTimer);
    this.tickTimer = null;
  }

  private isMarketOpenNow(): boolean {
    // NSE cash market (IST): Monday-Friday, 09:15 to 15:30.
    const now = new Date();
    const utcMinutes = now.getUTCHours() * 60 + now.getUTCMinutes();
    const istMinutesRaw = utcMinutes + 330;
    const day = now.getUTCDay();

    const adjustedDay = istMinutesRaw >= 1440 ? (day + 1) % 7 : day;
    const adjustedMinutes = istMinutesRaw >= 1440 ? istMinutesRaw - 1440 : istMinutesRaw;

    const isWeekday = adjustedDay >= 1 && adjustedDay <= 5;
    if (!isWeekday) return false;

    const marketOpenMin = 9 * 60 + 15;
    const marketCloseMin = 15 * 60 + 30;
    return adjustedMinutes >= marketOpenMin && adjustedMinutes <= marketCloseMin;
  }

  private applyTick(tick: DhanChartTickResponse): void {
    if (!this.mainSeries) return;

    const merged = this.mergeTickIntoCandles(this.liveCandles, tick);
    this.applyCandlesToChart(merged, this.liveResolvedTimeframe, false);
    this.liveLastPrice = Number(tick.price);
    this.liveChartUpdatedAt = new Date(Number(tick.timestamp) * 1000);

    const cacheKey = this.getChartCacheKey(this.symbol, this.liveTimeframe);
    const cached = this.candleCache.get(cacheKey);
    if (cached) {
      cached.candles = merged;
      cached.lastPrice = this.liveLastPrice;
      cached.updatedAt = new Date();
      this.candleCache.set(cacheKey, cached);
    }
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

  private formatSignedNumber(value: unknown): string {
    const n = Number(value);
    if (!Number.isFinite(n)) return '--';
    const abs = Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
    return `${n >= 0 ? '+' : '-'}${abs}`;
  }

  private resolveChartErrorMessage(err: HttpErrorResponse): string {
    const detail = err?.error?.detail;
    if (typeof detail === 'string' && detail.length > 0) {
      if (detail.includes('Security ID is required')) {
        return 'Live chart unavailable: Dhan security mapping is missing for this stock symbol.';
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
