import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { LucideAngularModule } from 'lucide-angular';

import { DhanChartCandle, DhanLiveChartService } from '../../core/services/dhan-live-chart.service';

interface MAScreenerRow {
  symbol: string;
  close: number | null;
  ma50: number | null;
  ma100: number | null;
  ma200: number | null;
  momentum10: number | null;
  signal: 'Bullish' | 'Bearish' | 'Mixed' | 'N/A';
  error?: string;
}

@Component({
  selector: 'app-moving-averages',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, LucideAngularModule],
  templateUrl: './moving-averages.component.html',
  styleUrl: './moving-averages.component.scss',
})
export class MovingAveragesComponent implements OnInit {
  symbolsText = 'RELIANCE, TCS, INFY, HDFCBANK, AXISBANK';
  loading = false;
  error = '';
  query = '';
  signalFilter: 'all' | 'bullish' | 'bearish' | 'mixed' | 'na' = 'all';
  rows: MAScreenerRow[] = [];

  constructor(private dhanLiveChartService: DhanLiveChartService) {}

  ngOnInit(): void {
    this.runScan();
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

    const symbols = Array.from(new Set(
      this.symbolsText
        .split(',')
        .map((s) => s.trim().toUpperCase())
        .filter((s) => !!s)
    )).slice(0, 30);

    if (symbols.length === 0) {
      this.rows = [];
      this.loading = false;
      this.error = 'Enter at least one symbol.';
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
    const close = candles.length ? Number(candles[candles.length - 1].close) : null;
    const ma50 = this.calculateMA(candles, 50);
    const ma100 = this.calculateMA(candles, 100);
    const ma200 = this.calculateMA(candles, 200);
    const momentum10 = this.calculateMomentum(candles, 10);

    let signal: MAScreenerRow['signal'] = 'N/A';
    if (this.isFiniteNumber(close) && this.isFiniteNumber(ma50) && this.isFiniteNumber(ma100) && this.isFiniteNumber(ma200)) {
      if (close > ma50 && ma50 > ma100 && ma100 > ma200) {
        signal = 'Bullish';
      } else if (close < ma50 && ma50 < ma100 && ma100 < ma200) {
        signal = 'Bearish';
      } else {
        signal = 'Mixed';
      }
    }

    return {
      symbol,
      close,
      ma50,
      ma100,
      ma200,
      momentum10,
      signal,
    };
  }

  private calculateMA(candles: DhanChartCandle[], length: number): number | null {
    if (candles.length < length) return null;
    let sum = 0;
    for (let i = candles.length - length; i < candles.length; i++) {
      const close = Number(candles[i].close);
      if (!Number.isFinite(close)) return null;
      sum += close;
    }
    return sum / length;
  }

  private calculateMomentum(candles: DhanChartCandle[], period: number): number | null {
    if (candles.length <= period) return null;
    const latest = Number(candles[candles.length - 1].close);
    const prior = Number(candles[candles.length - 1 - period].close);
    if (!Number.isFinite(latest) || !Number.isFinite(prior)) return null;
    return latest - prior;
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
