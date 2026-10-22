import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subject, catchError, debounceTime, distinctUntilChanged, firstValueFrom, map, of, switchMap, takeUntil } from 'rxjs';
import { LucideAngularModule } from 'lucide-angular';

import { DhanChartCandle, DhanLiveChartService } from '../../core/services/dhan-live-chart.service';
import { StockService, SymbolSearchResult } from '../../core/services/stock.service';
import { CompanyLogoComponent } from '../../shared/components/company-logo/company-logo.component';
import { TrendSignal, momentum, movingAverage, trendSignal } from '../../core/utils/moving-averages';

interface MAScreenerRow {
  symbol: string;
  close: number | null;
  ma50: number | null;
  ma100: number | null;
  ma200: number | null;
  momentum10: number | null;
  signal: TrendSignal;
  error?: string;
}

@Component({
  selector: 'app-moving-averages',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, LucideAngularModule, CompanyLogoComponent],
  templateUrl: './moving-averages.component.html',
  styleUrl: './moving-averages.component.scss',
})
export class MovingAveragesComponent implements OnInit, OnDestroy {
  readonly maxSymbols = 30;
  symbols: string[] = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'AXISBANK'];
  searchText = '';
  suggestions: SymbolSearchResult[] = [];
  activeIndex = 0;
  loading = false;
  error = '';
  query = '';
  signalFilter: 'all' | 'bullish' | 'bearish' | 'mixed' | 'na' = 'all';
  rows: MAScreenerRow[] = [];

  private searchSubject = new Subject<string>();
  private destroy$ = new Subject<void>();

  constructor(
    private dhanLiveChartService: DhanLiveChartService,
    private stockService: StockService,
  ) {}

  ngOnInit(): void {
    this.searchSubject
      .pipe(
        debounceTime(200),
        distinctUntilChanged(),
        // switchMap drops replies to older keystrokes, so suggestions never lag the input.
        switchMap((q) => q
          ? this.stockService.searchSymbols(q, 10).pipe(map((res) => res?.results ?? []), catchError(() => of([])))
          : of([])),
        takeUntil(this.destroy$),
      )
      .subscribe((results) => {
        this.suggestions = results.filter((r) => !this.symbols.includes(r.symbol));
        this.activeIndex = 0;
      });
    this.runScan();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onSearchInput(): void {
    this.searchSubject.next(this.searchText.trim().toUpperCase());
  }

  onSearchKeydown(event: KeyboardEvent): void {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!this.suggestions.length) return;
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      this.activeIndex = (this.activeIndex + step + this.suggestions.length) % this.suggestions.length;
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const pick = this.suggestions[this.activeIndex];
      if (pick) this.addSymbol(pick.symbol);
    } else if (event.key === 'Backspace' && !this.searchText && this.symbols.length) {
      this.symbols = this.symbols.slice(0, -1);
    } else if (event.key === 'Escape') {
      this.closeSuggestions();
    }
  }

  addSymbol(symbol: string): void {
    if (!this.symbols.includes(symbol) && this.symbols.length < this.maxSymbols) {
      this.symbols = [...this.symbols, symbol];
    }
    this.searchText = '';
    this.closeSuggestions();
  }

  removeSymbol(symbol: string): void {
    this.symbols = this.symbols.filter((s) => s !== symbol);
  }

  closeSuggestions(): void {
    this.suggestions = [];
    this.searchSubject.next('');  // so typing the same text again searches again
  }

  get filteredRows(): MAScreenerRow[] {
    const q = this.query.trim().toUpperCase();

    return this.rows.filter((row) => {
      const matchesQuery = !q || row.symbol.includes(q);
      if (!matchesQuery) return false;

      switch (this.signalFilter) {
        case 'bullish':
          return row.signal === 'Bullish';
        case 'bearish':
          return row.signal === 'Bearish';
        case 'mixed':
          return row.signal === 'Mixed';
        case 'na':
          return row.signal === 'N/A';
        case 'all':
        default:
          return true;
      }
    });
  }

  async runScan(): Promise<void> {
    this.loading = true;
    this.error = '';

    const symbols = this.symbols;

    if (symbols.length === 0) {
      this.rows = [];
      this.loading = false;
      this.error = 'Add at least one stock.';
      return;
    }

    const results: MAScreenerRow[] = [];

    for (const symbol of symbols) {
      try {
        const response = await firstValueFrom(
          this.dhanLiveChartService.getBootstrap({ symbol, timeframe: 'D' })
        );

        const candles = Array.isArray(response?.candles) ? response.candles : [];
        const row = this.buildRow(symbol, candles);
        results.push(row);
      } catch (err: any) {
        results.push({
          symbol,
          close: null,
          ma50: null,
          ma100: null,
          ma200: null,
          momentum10: null,
          signal: 'N/A',
          error: err?.error?.detail || 'Data unavailable',
        });
      }
    }

    this.rows = results;
    this.loading = false;
  }

  private buildRow(symbol: string, candles: DhanChartCandle[]): MAScreenerRow {
    const closes = candles.map((c) => Number(c.close));
    const close = closes.length ? closes[closes.length - 1] : null;
    const ma50 = movingAverage(closes, 50);
    const ma100 = movingAverage(closes, 100);
    const ma200 = movingAverage(closes, 200);
    return { symbol, close, ma50, ma100, ma200, momentum10: momentum(closes, 10), signal: trendSignal(close, ma50, ma100, ma200) };
  }

  private isFiniteNumber(value: unknown): value is number {
    return typeof value === 'number' && Number.isFinite(value);
  }

  formatNumber(value: number | null): string {
    if (!this.isFiniteNumber(value)) return '--';
    return value.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }

  formatSigned(value: number | null): string {
    if (!this.isFiniteNumber(value)) return '--';
    const abs = Math.abs(value).toLocaleString('en-IN', { maximumFractionDigits: 2 });
    return `${value >= 0 ? '+' : '-'}${abs}`;
  }
}
