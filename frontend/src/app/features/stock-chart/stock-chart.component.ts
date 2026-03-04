import { Component, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, Subscription } from 'rxjs';
import { debounceTime, distinctUntilChanged, switchMap } from 'rxjs/operators';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  LineData,
  HistogramData,
  ColorType,
  CrosshairMode,
  Time,
  CandlestickSeries,
  LineSeries,
  BarSeries,
  AreaSeries,
  BaselineSeries,
  HistogramSeries,
} from 'lightweight-charts';
import {
  ChartService,
  SearchResult,
  StockQuote,
  OHLCVData,
  Fundamental,
  NewsArticle,
  OptionEntry,
} from '../../core/services/chart.service';

type ChartType = 'candlestick' | 'line' | 'bar' | 'area' | 'baseline' | 'histogram';

interface PeriodOption {
  label: string;
  period: string;
  interval: string;
}

@Component({
  selector: 'app-stock-chart',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './stock-chart.component.html',
  styleUrl: './stock-chart.component.scss',
})
export class StockChartComponent implements OnInit, OnDestroy, AfterViewInit {
  @ViewChild('chartContainer') chartContainer!: ElementRef<HTMLDivElement>;

  // Search
  searchQuery = '';
  searchResults: SearchResult[] = [];
  showResults = false;
  private searchSubject = new Subject<string>();
  private searchSub?: Subscription;

  // Stock data
  selectedSymbol = '';
  quote: StockQuote | null = null;
  quoteLoading = false;
  private liveUpdateInterval: any;

  // Index Presets
  indexPresets = [
    { symbol: 'NIFTY', name: 'Nifty 50' },
    { symbol: 'NIFTY BANK', name: 'Nifty Bank' },
    { symbol: 'NIFTY IT', name: 'Nifty IT' },
    { symbol: 'NIFTY NEXT 50', name: 'Nifty Next 50' },
    { symbol: 'NIFTY AUTO', name: 'Nifty Auto' },
    { symbol: 'NIFTY METAL', name: 'Nifty Metal' }
  ];

  // Chart
  chart: IChartApi | null = null;
  mainSeries: ISeriesApi<any> | null = null;
  volumeSeries: ISeriesApi<'Histogram'> | null = null;
  chartData: OHLCVData[] = [];
  chartLoading = false;
  chartType: ChartType = 'candlestick';
  chartTypes: { value: ChartType; label: string }[] = [
    { value: 'candlestick', label: 'Candlestick' },
    { value: 'line', label: 'Line' },
    { value: 'bar', label: 'Bar' },
    { value: 'area', label: 'Mountain' },
    { value: 'baseline', label: 'Baseline' },
    { value: 'histogram', label: 'Histogram' },
  ];

  periods: PeriodOption[] = [
    { label: '1D', period: '1d', interval: '1m' },
    { label: '5D', period: '5d', interval: '5m' },
    { label: '1M', period: '1mo', interval: '1d' },
    { label: '3M', period: '3mo', interval: '1d' },
    { label: '6M', period: '6mo', interval: '1d' },
    { label: '1Y', period: '1y', interval: '1d' },
    { label: '2Y', period: '2y', interval: '1d' },
    { label: '5Y', period: '5y', interval: '1wk' },
    { label: 'Max', period: 'max', interval: '1mo' },
  ];
  activePeriod = '1y';

  // Detail tabs
  activeTab = 'fundamentals';
  fundamentals: Fundamental | null = null;
  news: NewsArticle[] = [];
  financials: any = null;
  financialStatement = 'income';
  optionDates: string[] = [];
  selectedOptionDate = '';
  optionCalls: OptionEntry[] = [];
  optionPuts: OptionEntry[] = [];
  tabLoading = false;

  private resizeObserver?: ResizeObserver;

  constructor(private chartService: ChartService) { }

  ngOnInit(): void {
    this.searchSub = this.searchSubject
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        switchMap((q) => this.chartService.searchTickers(q))
      )
      .subscribe((res) => {
        this.searchResults = res.results;
        this.showResults = res.results.length > 0;
      });

    // Load Nifty 50 by default
    this.selectPreset('NIFTY', 'Nifty 50');
  }

  ngAfterViewInit(): void {
    // Chart will be created when a stock is selected
  }

  ngOnDestroy(): void {
    this.searchSub?.unsubscribe();
    this.resizeObserver?.disconnect();
    this.chart?.remove();
    if (this.liveUpdateInterval) {
      clearInterval(this.liveUpdateInterval);
    }
  }

  onSearchInput(value: string): void {
    if (value.length >= 2) {
      this.searchSubject.next(value);
    } else {
      this.searchResults = [];
      this.showResults = false;
    }
  }

  selectStock(result: SearchResult): void {
    this.selectPreset(result.symbol, result.name);
  }

  selectPreset(symbol: string, name: string): void {
    this.selectedSymbol = symbol;
    this.searchQuery = `${symbol} — ${name}`;
    this.showResults = false;
    this.loadStock();
  }

  hideResults(): void {
    setTimeout(() => (this.showResults = false), 200);
  }

  loadStock(): void {
    if (!this.selectedSymbol) return;

    // Load quote
    this.quoteLoading = true;
    this.chartService.getQuote(this.selectedSymbol).subscribe({
      next: (q) => {
        this.quote = q;
        this.quoteLoading = false;
      },
      error: () => (this.quoteLoading = false),
    });

    // Load chart
    this.loadChartData();

    // Load default tab
    this.loadTabData();

    this.startLiveUpdates();
  }

  startLiveUpdates(): void {
    if (this.liveUpdateInterval) {
      clearInterval(this.liveUpdateInterval);
    }

    this.liveUpdateInterval = setInterval(() => {
      if (!this.selectedSymbol) return;
      this.chartService.getQuote(this.selectedSymbol).subscribe(q => {
        this.quote = q;

        // Update chart's last candle live if viewing 1D period
        if (this.activePeriod === '1d' && this.chartData.length > 0 && this.mainSeries) {
          const lastData = this.chartData[this.chartData.length - 1];

          // Update last candle data with current price
          lastData.close = q.price;
          if (q.price > lastData.high) lastData.high = q.price;
          if (q.price < lastData.low) lastData.low = q.price;
          lastData.volume = q.volume;

          // Format for lightweight charts
          let updatedPoint: any;
          if (['line', 'area', 'baseline', 'histogram'].includes(this.chartType)) {
            updatedPoint = { time: lastData.time as any, value: lastData.close };
          } else {
            updatedPoint = {
              time: lastData.time as any,
              open: lastData.open,
              high: lastData.high,
              low: lastData.low,
              close: lastData.close
            };
          }
          this.mainSeries.update(updatedPoint);

          if (this.volumeSeries) {
            this.volumeSeries.update({
              time: lastData.time as any,
              value: lastData.volume,
              color: lastData.close >= lastData.open ? 'rgba(0, 208, 132, 0.3)' : 'rgba(255, 71, 87, 0.3)'
            });
          }
        }
      });
    }, 10000); // Poll every 10 seconds to avoid Yahoo Finance rate limits
  }

  loadChartData(): void {
    const p = this.periods.find((x) => x.period === this.activePeriod) || this.periods[5];
    this.chartLoading = true;

    this.chartService.getHistory(this.selectedSymbol, p.period, p.interval).subscribe({
      next: (res) => {
        this.chartData = res.history;
        this.chartLoading = false;
        this.renderChart();
      },
      error: () => (this.chartLoading = false),
    });
  }

  setPeriod(period: string): void {
    this.activePeriod = period;
    this.loadChartData();
  }

  setChartType(type: ChartType): void {
    this.chartType = type;
    this.renderChart();
  }

  renderChart(): void {
    if (!this.chartContainer || this.chartData.length === 0) return;

    // Remove existing chart
    if (this.chart) {
      this.chart.remove();
      this.chart = null;
    }

    const container = this.chartContainer.nativeElement;

    this.chart = createChart(container, {
      width: container.clientWidth,
      height: 450,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: 'rgba(255, 255, 255, 0.7)',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
        timeVisible: this.activePeriod === '1d' || this.activePeriod === '5d',
      },
    });

    // Add main series based on chart type
    this.addMainSeries();

    // Add volume
    this.volumeSeries = this.chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    }) as any;
    this.chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    const volData: HistogramData[] = this.chartData.map((d) => ({
      time: d.time as Time,
      value: d.volume,
      color: d.close >= d.open ? 'rgba(0, 208, 132, 0.3)' : 'rgba(255, 71, 87, 0.3)',
    }));
    if (this.volumeSeries) {
      this.volumeSeries.setData(volData);
    }

    this.chart.timeScale().fitContent();

    // Responsive resize
    this.resizeObserver?.disconnect();
    this.resizeObserver = new ResizeObserver(() => {
      if (this.chart) {
        this.chart.applyOptions({ width: container.clientWidth });
      }
    });
    this.resizeObserver.observe(container);
  }

  private addMainSeries(): void {
    if (!this.chart) return;

    switch (this.chartType) {
      case 'candlestick': {
        this.mainSeries = this.chart.addSeries(CandlestickSeries, {
          upColor: '#00d084',
          downColor: '#ff4757',
          borderUpColor: '#00d084',
          borderDownColor: '#ff4757',
          wickUpColor: '#00d084',
          wickDownColor: '#ff4757',
        });
        const candleData: CandlestickData[] = this.chartData.map((d) => ({
          time: d.time as Time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
        }));
        this.mainSeries.setData(candleData);
        break;
      }
      case 'line': {
        this.mainSeries = this.chart.addSeries(LineSeries, {
          color: '#667eea',
          lineWidth: 2,
        });
        const lineData: LineData[] = this.chartData.map((d) => ({
          time: d.time as Time,
          value: d.close,
        }));
        this.mainSeries.setData(lineData);
        break;
      }
      case 'bar': {
        this.mainSeries = this.chart.addSeries(BarSeries, {
          upColor: '#00d084',
          downColor: '#ff4757',
        });
        const barData: CandlestickData[] = this.chartData.map((d) => ({
          time: d.time as Time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
        }));
        this.mainSeries.setData(barData);
        break;
      }
      case 'area': {
        this.mainSeries = this.chart.addSeries(AreaSeries, {
          topColor: 'rgba(102, 126, 234, 0.4)',
          bottomColor: 'rgba(102, 126, 234, 0.0)',
          lineColor: '#667eea',
          lineWidth: 2,
        });
        const areaData: LineData[] = this.chartData.map((d) => ({
          time: d.time as Time,
          value: d.close,
        }));
        this.mainSeries.setData(areaData);
        break;
      }
      case 'baseline': {
        const avgPrice =
          this.chartData.reduce((s, d) => s + d.close, 0) / this.chartData.length;
        this.mainSeries = this.chart.addSeries(BaselineSeries, {
          baseValue: { type: 'price', price: avgPrice },
          topLineColor: '#00d084',
          topFillColor1: 'rgba(0, 208, 132, 0.3)',
          topFillColor2: 'rgba(0, 208, 132, 0.0)',
          bottomLineColor: '#ff4757',
          bottomFillColor1: 'rgba(255, 71, 87, 0.0)',
          bottomFillColor2: 'rgba(255, 71, 87, 0.3)',
        });
        const baseData: LineData[] = this.chartData.map((d) => ({
          time: d.time as Time,
          value: d.close,
        }));
        this.mainSeries.setData(baseData);
        break;
      }
      case 'histogram': {
        this.mainSeries = this.chart.addSeries(HistogramSeries, {
          color: '#667eea',
        });
        const histData: HistogramData[] = this.chartData.map((d) => ({
          time: d.time as Time,
          value: d.close,
          color: d.close >= d.open ? '#00d084' : '#ff4757',
        }));
        this.mainSeries.setData(histData);
        break;
      }
    }
  }

  // Tab management
  setActiveTab(tab: string): void {
    this.activeTab = tab;
    this.loadTabData();
  }

  loadTabData(): void {
    if (!this.selectedSymbol) return;
    this.tabLoading = true;

    switch (this.activeTab) {
      case 'fundamentals':
        this.chartService.getFundamentals(this.selectedSymbol).subscribe({
          next: (f) => {
            this.fundamentals = f;
            this.tabLoading = false;
          },
          error: () => (this.tabLoading = false),
        });
        break;
      case 'news':
        this.chartService.getNews(this.selectedSymbol).subscribe({
          next: (n) => {
            this.news = n.articles;
            this.tabLoading = false;
          },
          error: () => (this.tabLoading = false),
        });
        break;
      case 'financials':
        this.chartService.getFinancials(this.selectedSymbol, this.financialStatement).subscribe({
          next: (f) => {
            this.financials = f;
            this.tabLoading = false;
          },
          error: () => (this.tabLoading = false),
        });
        break;
      case 'options':
        this.chartService.getOptionDates(this.selectedSymbol).subscribe({
          next: (d) => {
            this.optionDates = d.dates;
            if (d.dates.length > 0) {
              this.selectedOptionDate = d.dates[0];
              this.loadOptionChain();
            } else {
              this.tabLoading = false;
            }
          },
          error: () => (this.tabLoading = false),
        });
        break;
    }
  }

  loadOptionChain(): void {
    if (!this.selectedOptionDate) return;
    this.tabLoading = true;
    this.chartService
      .getOptionChain(this.selectedSymbol, this.selectedOptionDate)
      .subscribe({
        next: (chain) => {
          this.optionCalls = chain.calls;
          this.optionPuts = chain.puts;
          this.tabLoading = false;
        },
        error: () => (this.tabLoading = false),
      });
  }

  onOptionDateChange(): void {
    this.loadOptionChain();
  }

  onFinancialStatementChange(): void {
    this.loadTabData();
  }

  formatNumber(n: number): string {
    if (!n && n !== 0) return '—';
    const absN = Math.abs(n);
    const sign = n < 0 ? '-' : '';
    if (absN >= 1e7) return sign + '₹' + (absN / 1e7).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + 'Cr';
    if (absN >= 1e5) return sign + '₹' + (absN / 1e5).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + 'L';
    return sign + '₹' + absN.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }

  formatPct(n: number): string {
    if (!n) return '—';
    return (n * 100).toFixed(2) + '%';
  }

  getFinancialPeriods(): string[] {
    if (!this.financials?.data) return [];
    return Object.keys(this.financials.data);
  }

  getFinancialRows(): string[] {
    const periods = this.getFinancialPeriods();
    if (periods.length === 0) return [];
    return Object.keys(this.financials.data[periods[0]] || {});
  }

  getFinancialValue(period: string, row: string): number {
    return this.financials?.data?.[period]?.[row] ?? 0;
  }
}
