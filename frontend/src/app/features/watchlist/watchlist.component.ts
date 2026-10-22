import { AfterViewInit, Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { Subscription } from 'rxjs';
import {
  AreaSeries,
  BarData,
  BarSeries,
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
  BaselineSeries,
  createChart,
} from 'lightweight-charts';

import { PortfolioService } from '../../core/services/portfolio.service';
import { StockService, SymbolSearchResult } from '../../core/services/stock.service';
import { ThemeService } from '../../core/services/theme.service';
import {
  ChartTimeframe,
  DhanChartRequest,
  DhanDepthLevel,
  DhanLiveChartService,
  depthNote,
} from '../../core/services/dhan-live-chart.service';
import { MarketStreamMessage, MarketStreamRequest, MarketStreamService, StreamCandle } from '../../core/services/market-stream.service';
import { CompanyLogoComponent } from '../../shared/components/company-logo/company-logo.component';

const toCandle = (c: StreamCandle): CandlestickData => ({
  time: c[0] as UTCTimestamp, open: c[1], high: c[2], low: c[3], close: c[4],
});

type ChartDisplayType = 'candlestick' | 'line' | 'bar' | 'area' | 'baseline';
type FocusPanel = 'chart' | 'depth';

@Component({
  selector: 'app-watchlist',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, CompanyLogoComponent],
  templateUrl: './watchlist.component.html',
  styleUrl: './watchlist.component.scss',
})
export class WatchlistComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('watchlistChartHost') chartHost?: ElementRef<HTMLDivElement>;

  readonly defaultWatchSymbols = ['AXISBANK', 'RELIANCE', 'INFY', 'TCS', 'HDFCBANK'];
  watchInput = '';
  watchSymbols: string[] = [];
  watchInputError = '';
  watchSuggestions: SymbolSearchResult[] = [];
  showWatchSuggestions = false;
  portfolioSymbols: string[] = [];
  selectedSymbol = 'AXISBANK';
  focusPanel: FocusPanel = 'chart';
  currentPage = 1;
  readonly watchPageSize = 5;

  chartType: ChartDisplayType = 'candlestick';
  liveTimeframe: ChartTimeframe = '5';
  dailyRange: '1D' | '5D' | '1M' | '3M' | '6M' | '1Y' | '2Y' | '5Y' | '10Y' | 'MAX' = 'MAX';
  readonly dailyRangeOptions: Array<'1D' | '5D' | '1M' | '3M' | '6M' | '1Y' | '2Y' | '5Y' | '10Y' | 'MAX'> =
    ['1D', '5D', '1M', '3M', '6M', '1Y', '2Y', '5Y', '10Y', 'MAX'];
  liveChartLoading = false;
  liveChartError = '';
  liveTransportStatus: 'idle' | 'connecting' | 'ws' | 'polling' | 'closed' = 'idle';
  liveChartSource: 'live' | 'cache' | 'stale' = 'stale';
  liveCandleCount = 0;
  liveLastPrice = 0;

  marketDepthLoading = false;
  marketDepthError = '';
  marketDepthLimit = 20;
  marketDepthBuy: DhanDepthLevel[] = [];
  marketDepthSell: DhanDepthLevel[] = [];
  marketDepthNote = '';
  hoveredCandle: CandlestickData | null = null;
  lastVisibleCandle: CandlestickData | null = null;

  private chartApi: IChartApi | null = null;
  private mainSeries: ISeriesApi<any> | null = null;
  private liveCandles: CandlestickData[] = [];
  private resolvedTimeframe: ChartTimeframe = '5';
  private resizeObserver: ResizeObserver | null = null;
  private liveSub: Subscription | null = null;
  private chartLoadSub: Subscription | null = null;
  private addSearchTimer: ReturnType<typeof setTimeout> | null = null;
  private themeSub?: Subscription;
  private isDarkTheme = false;
  private readonly watchlistStorageKey = 'stocksage.watchlist.symbols';
  private readonly candleCache = new Map<string, {
    candles: CandlestickData[];
    resolvedTimeframe: ChartTimeframe;
    updatedAt: number;
    source: 'live' | 'cache' | 'stale';
  }>();
  private readonly onCrosshairMove = (param: MouseEventParams<Time>) => {
    const unix = this.toUnixFromChartTime(param.time as Time);
    if (!unix || this.liveCandles.length === 0) {
      this.hoveredCandle = null;
      return;
    }

    this.hoveredCandle = this.liveCandles.find((c) => Number(c.time) === unix) || null;
  };

  constructor(
    private stockService: StockService,
    private portfolioService: PortfolioService,
    private dhanLiveChartService: DhanLiveChartService,
    private marketStream: MarketStreamService,
    private themeService: ThemeService,
  ) {}

  ngOnInit(): void {
    this.themeSub = this.themeService.isDarkTheme$.subscribe((isDark) => {
      this.isDarkTheme = isDark;
      requestAnimationFrame(() => this.applyChartTheme());
    });

    this.watchSymbols = this.loadWatchSymbols();
    this.selectedSymbol = this.watchSymbols[0] || this.defaultWatchSymbols[0];

    this.stockService.getSymbols().subscribe({
      next: (res) => {
        const symbols = Array.isArray(res?.symbols) ? res.symbols : [];
        if (symbols.length > 0 && this.watchSymbols.length === 0) {
          this.watchSymbols = this.defaultWatchSymbols.slice();
          this.selectedSymbol = this.watchSymbols[0];
          this.persistWatchSymbols();
        }
      },
      error: () => {},
    });

    this.portfolioService.getHoldings().subscribe({
      next: (res) => {
        const holdings = Array.isArray(res?.holdings) ? res.holdings : [];
        this.portfolioSymbols = Array.from(new Set(holdings.map((h) => String(h.symbol || '').toUpperCase()).filter((s) => !!s)));
      },
      error: () => {
        this.portfolioSymbols = [];
      },
    });
  }

  ngAfterViewInit(): void {
    this.initChart();
    this.loadChart();
    this.loadMarketDepth(20);
  }

  ngOnDestroy(): void {
    this.themeSub?.unsubscribe();
    this.stopLiveUpdates();
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    if (this.chartApi) {
      this.chartApi.unsubscribeCrosshairMove(this.onCrosshairMove);
      this.chartApi.remove();
      this.chartApi = null;
    }
    if (this.addSearchTimer) {
      clearTimeout(this.addSearchTimer);
      this.addSearchTimer = null;
    }
    this.mainSeries = null;
  }

  get pagedWatchSymbols(): string[] {
    const start = (this.currentPage - 1) * this.watchPageSize;
    return this.watchSymbols.slice(start, start + this.watchPageSize);
  }

  get totalPages(): number {
    return Math.max(1, Math.ceil(this.watchSymbols.length / this.watchPageSize));
  }

  setTimeframe(tf: ChartTimeframe): void {
    if (this.liveTimeframe === tf) return;
    this.liveTimeframe = tf;
    if (tf === 'D') {
      this.dailyRange = 'MAX';
    }
    this.loadChart();
  }

  setDailyRange(range: '1D' | '5D' | '1M' | '3M' | '6M' | '1Y' | '2Y' | '5Y' | '10Y' | 'MAX'): void {
    if (this.dailyRange === range) return;
    this.dailyRange = range;
    this.applyDailyRangeFromCache();
  }

  setChartType(type: ChartDisplayType): void {
    if (this.chartType === type) return;
    this.chartType = type;
    this.recreateMainSeries();
    this.applyCandles(this.liveCandles);
  }

  selectSymbol(symbol: string, panel: FocusPanel = 'chart'): void {
    if (!symbol) return;
    this.selectedSymbol = symbol.toUpperCase();
    this.focusPanel = panel;
    this.loadChart();
    this.loadMarketDepth(this.marketDepthLimit as 20 | 200);
  }

  setDepthLimit(limit: 20 | 200): void {
    if (this.marketDepthLimit === limit && (this.marketDepthBuy.length || this.marketDepthSell.length)) return;
    this.loadMarketDepth(limit);
  }

  onWatchInputChange(): void {
    this.watchInputError = '';
    const query = this.watchInput.trim().toUpperCase();

    if (this.addSearchTimer) {
      clearTimeout(this.addSearchTimer);
      this.addSearchTimer = null;
    }

    if (query.length < 2) {
      this.watchSuggestions = [];
      this.showWatchSuggestions = false;
      return;
    }

    this.addSearchTimer = setTimeout(() => {
      this.stockService.searchSymbols(query, 8).subscribe({
        next: (res) => {
          const items = Array.isArray(res?.results) ? res.results : [];
          this.watchSuggestions = items;
          this.showWatchSuggestions = items.length > 0;
        },
        error: () => {
          this.watchSuggestions = [];
          this.showWatchSuggestions = false;
        },
      });
    }, 200);
  }

  selectWatchSuggestion(symbol: string): void {
    this.watchInput = String(symbol || '').trim().toUpperCase();
    this.watchSuggestions = [];
    this.showWatchSuggestions = false;
  }

  hideWatchSuggestions(): void {
    setTimeout(() => {
      this.showWatchSuggestions = false;
    }, 120);
  }

  addWatchSymbol(): void {
    this.watchInputError = '';
    const symbol = this.normalizeWatchSymbol(this.watchInput);

    if (!symbol) {
      this.watchInputError = 'Enter a symbol to add.';
      return;
    }

    if (this.watchSymbols.includes(symbol)) {
      this.selectSymbol(symbol, this.focusPanel);
      this.watchInput = '';
      this.watchSuggestions = [];
      this.showWatchSuggestions = false;
      return;
    }

    if (!/^[A-Z0-9.-]{2,40}$/.test(symbol)) {
      this.watchInputError = 'Enter a valid stock or option symbol.';
      return;
    }

    this.watchSymbols = [symbol, ...this.watchSymbols];
    this.persistWatchSymbols();
    this.currentPage = 1;
    this.selectSymbol(symbol, this.focusPanel);
    this.watchInput = '';
    this.watchSuggestions = [];
    this.showWatchSuggestions = false;
  }

  removeWatchSymbol(symbol: string, event?: Event): void {
    event?.stopPropagation();
    const normalized = this.normalizeWatchSymbol(symbol);
    if (!normalized) return;

    this.watchSymbols = this.watchSymbols.filter((s) => s !== normalized);
    if (this.watchSymbols.length === 0) {
      this.watchSymbols = this.defaultWatchSymbols.slice();
    }

    if (this.currentPage > this.totalPages) {
      this.currentPage = this.totalPages;
    }

    if (this.selectedSymbol === normalized) {
      this.selectedSymbol = this.watchSymbols[0];
      this.loadChart();
      this.loadMarketDepth(this.marketDepthLimit as 20 | 200);
    }

    this.persistWatchSymbols();
  }

  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages) return;
    this.currentPage = page;
  }

  private initChart(): void {
    const container = this.chartHost?.nativeElement;
    if (!container) return;

    const dark = this.isDarkModeFromDom();
    const cardBg = this.getThemeColor('--card', dark ? '#0b1020' : '#ffffff');
    const fg = this.getThemeColor('--foreground', dark ? '#cbd5e1' : '#334155');
    const border = this.getThemeColor('--border', dark ? 'rgba(255, 255, 255, 0.18)' : 'rgba(148, 163, 184, 0.35)');

    this.chartApi = createChart(container, {
      width: Math.max(340, container.clientWidth),
      height: 340,
      layout: {
        background: { type: ColorType.Solid, color: cardBg },
        textColor: fg,
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
    this.chartApi.subscribeCrosshairMove(this.onCrosshairMove);

    this.resizeObserver = new ResizeObserver((entries) => {
      const first = entries[0];
      if (!first || !this.chartApi) return;
      this.chartApi.applyOptions({ width: Math.max(340, Math.floor(first.contentRect.width)) });
    });

    this.resizeObserver.observe(container);
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
          topColor: 'rgba(2, 132, 199, 0.22)',
          bottomColor: 'rgba(2, 132, 199, 0.03)',
        });
        break;
      case 'baseline':
        this.mainSeries = this.chartApi.addSeries(BaselineSeries, {
          topLineColor: '#16a34a',
          topFillColor1: 'rgba(22, 163, 74, 0.16)',
          topFillColor2: 'rgba(22, 163, 74, 0.04)',
          bottomLineColor: '#dc2626',
          bottomFillColor1: 'rgba(220, 38, 38, 0.16)',
          bottomFillColor2: 'rgba(220, 38, 38, 0.04)',
          baseValue: { type: 'price', price: this.liveLastPrice || 0 },
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

  private loadChart(): void {
    this.stopLiveUpdates();
    this.liveChartError = '';
    if (this.liveTimeframe !== 'D') {
      this.watchLive();
      return;
    }

    // Daily candles come from REST history; intraday is streamed (watchLive).
    this.liveChartLoading = true;
    this.liveTransportStatus = 'idle';
    this.resolvedTimeframe = 'D';
    const cacheKey = this.getChartCacheKey(this.selectedSymbol, 'D');
    const cached = this.candleCache.get(cacheKey);
    if (cached && (Date.now() - cached.updatedAt) <= this.getCacheTtlMs('D')) {
      this.applyCandles(this.filterDailyCandles(cached.candles));
      this.liveChartSource = cached.source;
      this.liveChartLoading = false;
      return;
    }

    this.chartLoadSub = this.dhanLiveChartService.getBootstrap(this.getChartRequest()).subscribe({
      next: (res) => {
        const candles = (Array.isArray(res?.candles) ? res.candles : [])
          .map((c) => ({
            time: Number(c.time) as UTCTimestamp,
            open: Number(c.open),
            high: Number(c.high),
            low: Number(c.low),
            close: Number(c.close),
          }))
          .filter((c) => Number.isFinite(Number(c.time)) && Number.isFinite(c.open) && Number.isFinite(c.high) && Number.isFinite(c.low) && Number.isFinite(c.close));

        this.applyCandles(this.filterDailyCandles(candles));
        this.liveChartSource = String(res?.source || 'live') === 'cache' ? 'cache' : 'live';
        this.candleCache.set(cacheKey, { candles, resolvedTimeframe: 'D', updatedAt: Date.now(), source: this.liveChartSource });
        this.liveChartLoading = false;
      },
      error: (err: HttpErrorResponse) => {
        this.liveChartLoading = false;
        this.liveChartError = err?.error?.detail || 'Chart data unavailable.';
      },
    });
  }

  /** Intraday: a snapshot of about a week of candles, then live deltas (backend/market/service.py). */
  private watchLive(): void {
    this.liveChartLoading = true;
    this.liveTransportStatus = 'connecting';
    this.resolvedTimeframe = this.liveTimeframe;
    this.liveSub = this.marketStream
      .watch({ symbol: this.selectedSymbol, tf: this.liveTimeframe as MarketStreamRequest['tf'] })
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
      this.applyCandles(msg.candles.map(toCandle), false);
      this.showRecentBars();
      this.liveChartLoading = false;
      this.liveChartSource = 'live';
      this.liveChartError = '';
      this.liveTransportStatus = msg.source === 'rest' ? 'polling' : msg.market === 'open' ? 'ws' : 'closed';
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

  private applyCandles(candles: CandlestickData[], fit = true): void {
    this.liveCandles = candles;
    this.lastVisibleCandle = candles.length ? candles[candles.length - 1] : null;
    if (this.hoveredCandle) {
      const hoveredUnix = Number(this.hoveredCandle.time);
      this.hoveredCandle = candles.find((c) => Number(c.time) === hoveredUnix) || null;
    }
    this.mainSeries?.setData(candles.map((c) => this.toSeriesPoint(c)) as any);
    this.liveCandleCount = candles.length;
    this.liveLastPrice = candles.length ? Number(candles[candles.length - 1].close) : 0;
    if (fit) this.chartApi?.timeScale().fitContent();
  }

  private stopLiveUpdates(): void {
    this.liveSub?.unsubscribe();
    this.liveSub = null;
    this.chartLoadSub?.unsubscribe();
    this.chartLoadSub = null;
  }

  private loadMarketDepth(limit: 20 | 200): void {
    this.marketDepthLoading = true;
    this.marketDepthError = '';
    this.marketDepthLimit = limit;

    this.dhanLiveChartService.getMarketDepth(this.getChartRequest(), limit).subscribe({
      next: (res: any) => {
        this.marketDepthBuy = Array.isArray(res?.buy) ? res.buy : [];
        this.marketDepthSell = Array.isArray(res?.sell) ? res.sell : [];
        this.marketDepthNote = depthNote(res);
        this.marketDepthLoading = false;
      },
      error: (err: HttpErrorResponse) => {
        this.marketDepthLoading = false;
        this.marketDepthError = err?.error?.detail || 'Depth data unavailable.';
      },
    });
  }

  private getChartRequest(): DhanChartRequest {
    return {
      symbol: this.selectedSymbol,
      timeframe: this.liveTimeframe,
    };
  }

  trackBySymbol(_idx: number, symbol: string): string {
    return symbol;
  }

  formatPrice(v: unknown): string {
    const n = Number(v);
    if (!Number.isFinite(n)) return '--';
    return n.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }

  formatQty(v: unknown): string {
    const n = Number(v);
    if (!Number.isFinite(n)) return '--';
    return n.toLocaleString('en-IN');
  }

  get chartSourceLabel(): string {
    return this.liveChartSource === 'cache' ? 'Cached' : 'Live';
  }

  get transportLabel(): string {
    switch (this.liveTransportStatus) {
      case 'ws':
        return 'Live';
      case 'polling':
        return 'Polling';
      case 'connecting':
        return 'Connecting';
      case 'closed':
        return 'Closed';
      case 'idle':
      default:
        return 'Idle';
    }
  }

  get transportClass(): string {
    return `transport-${this.liveTransportStatus}`;
  }

  get activeCandle(): CandlestickData | null {
    return this.hoveredCandle ?? this.lastVisibleCandle;
  }

  isSelected(symbol: string): boolean {
    return this.selectedSymbol === symbol;
  }

  private getChartCacheKey(symbol: string, timeframe: ChartTimeframe): string {
    return `${symbol}:${timeframe}`;
  }

  private getCacheTtlMs(timeframe: ChartTimeframe): number {
    return timeframe === 'D' ? 10 * 60_000 : 45_000;
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
    if (!candles.length || this.dailyRange === 'MAX') return candles;
    const days = this.getRangeDays(this.dailyRange);
    if (!days) return candles;

    const last = Number(candles[candles.length - 1].time);
    const cutoff = last - (days * 24 * 60 * 60);
    const filtered = candles.filter((c) => Number(c.time) >= cutoff);
    return filtered.length ? filtered : candles;
  }

  private applyDailyRangeFromCache(): void {
    if (this.liveTimeframe !== 'D') return;
    const cacheKey = this.getChartCacheKey(this.selectedSymbol, 'D');
    const cached = this.candleCache.get(cacheKey);
    if (!cached || !cached.candles.length) return;
    this.applyCandles(this.filterDailyCandles(cached.candles));
  }

  private toUnixFromChartTime(time: Time): number {
    if (typeof time === 'number') return Number(time);
    if (typeof time === 'string') {
      const parsed = Date.parse(time);
      return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : 0;
    }

    const year = Number((time as { year: number }).year);
    const month = Number((time as { month: number }).month);
    const day = Number((time as { day: number }).day);
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return 0;
    return Math.floor(Date.UTC(year, month - 1, day) / 1000);
  }

  private formatIstTime(time: Time): string {
    const unix = this.toUnixFromChartTime(time);
    if (!unix) return '';

    if (this.resolvedTimeframe === 'D') {
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

  private normalizeWatchSymbol(value: string): string {
    return String(value || '').trim().toUpperCase();
  }

  private persistWatchSymbols(): void {
    try {
      localStorage.setItem(this.watchlistStorageKey, JSON.stringify(this.watchSymbols));
    } catch {
      // Ignore storage failures.
    }
  }

  private loadWatchSymbols(): string[] {
    try {
      const raw = localStorage.getItem(this.watchlistStorageKey);
      if (!raw) return this.defaultWatchSymbols.slice();

      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return this.defaultWatchSymbols.slice();

      const cleaned = parsed
        .map((v) => this.normalizeWatchSymbol(String(v || '')))
        .filter((s) => !!s)
        .slice(0, 300);

      const unique = Array.from(new Set(cleaned));
      return unique.length > 0 ? unique : this.defaultWatchSymbols.slice();
    } catch {
      return this.defaultWatchSymbols.slice();
    }
  }
}
