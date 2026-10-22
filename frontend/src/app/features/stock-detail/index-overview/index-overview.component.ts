import { Component, Input, OnChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

import { IndexAnalysis, IndexConstituent } from '../../../core/services/stock.service';
import { CompanyLogoComponent } from '../../../shared/components/company-logo/company-logo.component';

/** The index-only sections of the stock page: overview, breadth, movers, industries, constituents. */
@Component({
  selector: 'app-index-overview',
  standalone: true,
  imports: [CommonModule, RouterLink, CompanyLogoComponent],
  templateUrl: './index-overview.component.html',
  styleUrl: './index-overview.component.scss',
})
export class IndexOverviewComponent implements OnChanges {
  @Input({ required: true }) data!: IndexAnalysis;

  showAllConstituents = false;

  ngOnChanges(): void {
    this.showAllConstituents = false;  // a different index starts on its top 10 again
  }

  /** 1W / 1M / 1Y index returns from NSE's overview (1W is worked out from the week-ago level). */
  get indexReturns(): Array<{ label: string; pct: number }> {
    const o = this.data?.overview;
    if (!o?.last) return [];
    const weekPct = o.oneWeekAgoVal ? ((o.last - o.oneWeekAgoVal) / o.oneWeekAgoVal) * 100 : null;
    return [
      { label: '1 Week', pct: weekPct },
      { label: '1 Month', pct: o.perChange30d },
      { label: '1 Year', pct: o.perChange365d },
    ].filter((r): r is { label: string; pct: number } => r.pct != null);
  }

  get indexStats(): Array<{ label: string; value: string }> {
    const o = this.data?.overview;
    if (!o) return [];
    return [
      { label: 'Open', value: this.formatNumber(o.open) },
      { label: 'High', value: this.formatNumber(o.high) },
      { label: 'Low', value: this.formatNumber(o.low) },
      { label: 'Prev Close', value: this.formatNumber(o.previousClose) },
      { label: '52W High', value: this.formatNumber(o.yearHigh) },
      { label: '52W Low', value: this.formatNumber(o.yearLow) },
      { label: 'P/E', value: this.formatNumber(o.pe) },
      { label: 'P/B', value: this.formatNumber(o.pb) },
      { label: 'Dividend Yield', value: o.dy == null ? '--' : `${o.dy}%` },
    ];
  }

  /** Rising / unchanged / falling members: NSE's live count when available, else from the bhavcopy. */
  get indexBreadth(): { up: number; flat: number; down: number; total: number } | null {
    const o = this.data?.overview;
    const c = this.data?.constituents;
    const up = o?.advances ?? c?.advances;
    const down = o?.declines ?? c?.declines;
    if (up == null || down == null) return null;
    const flat = o?.unchanged ?? c?.unchanged ?? 0;
    const total = up + down + flat;
    return total ? { up, flat, down, total } : null;
  }

  get topGainers(): IndexConstituent[] {
    return (this.data?.constituents?.rows ?? []).filter((r) => (r.pct ?? 0) > 0).slice(0, 5);
  }

  get topLosers(): IndexConstituent[] {
    return (this.data?.constituents?.rows ?? []).filter((r) => (r.pct ?? 0) < 0).slice(-5).reverse();
  }

  get visibleConstituents(): IndexConstituent[] {
    const rows = this.data?.constituents?.rows ?? [];
    return this.showAllConstituents ? rows : rows.slice(0, 10);
  }

  /** Widest industry average move, to scale the industry bars. */
  get industryScale(): number {
    return Math.max(0.5, ...(this.data?.constituents?.industries ?? []).map((i) => Math.abs(i.avgPct)));
  }

  private formatNumber(value: unknown): string {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '--';
  }
}
