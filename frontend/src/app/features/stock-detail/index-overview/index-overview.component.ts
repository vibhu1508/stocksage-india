import { Component, Input, OnChanges, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';

import { LiveQuote, MarketStreamService } from '../../../core/services/market-stream.service';
import { IndexAnalysis, IndexConstituent, IndexConstituents, StockService } from '../../../core/services/stock.service';
import { CompanyLogoComponent } from '../../../shared/components/company-logo/company-logo.component';
import { FlashDirective } from '../../../shared/directives/flash.directive';
import { ShortNamePipe } from '../../../shared/pipes/short-name.pipe';

const LIVE_ROWS = 50;  // live quotes for at most this many rows at once (each one is a feed subscription)
const LIVE_POLL_MS = 15_000;  // the server works the moves out once per 10 s for everyone
const IDLE_POLL_MS = 300_000;  // outside the session: check now and then for the open

/** The index-only sections of the stock page: overview, breadth, movers, industries, constituents. */
@Component({
  selector: 'app-index-overview',
  standalone: true,
  imports: [CommonModule, RouterLink, CompanyLogoComponent, ShortNamePipe, FlashDirective],
  templateUrl: './index-overview.component.html',
  styleUrl: './index-overview.component.scss',
})
export class IndexOverviewComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) data!: IndexAnalysis;

  private stream = inject(MarketStreamService);
  private stocks = inject(StockService);
  showAllConstituents = false;
  live: Record<string, LiveQuote> = {};
  private liveSubs = new Map<string, Subscription>();
  /** Movers, breadth, industries and prices from the live feed during the session; null = end-of-day. */
  liveMoves: IndexConstituents | null = null;
  /** After 15:30 the live moves use last-trade prices; NSE's official closes come with the bhavcopy. */
  liveIsFinalSession = false;
  private liveRows = new Map<string, IndexConstituent>();
  private pollTimer?: ReturnType<typeof setTimeout>;
  private pollReq?: Subscription;

  ngOnChanges(): void {
    this.showAllConstituents = false;  // a different index starts on its top 10 again
    this.setLiveMoves(null);
    this.syncLive();
    this.pollLive();
  }

  ngOnDestroy(): void {
    this.liveSubs.forEach((s) => s.unsubscribe());
    clearTimeout(this.pollTimer);
    this.pollReq?.unsubscribe();
  }

  /** End-of-day constituents, or the live ones while the session's moves are streaming. */
  get moves(): IndexConstituents | null {
    return this.liveMoves ?? this.data?.constituents ?? null;
  }

  private pollLive(): void {
    clearTimeout(this.pollTimer);
    this.pollReq?.unsubscribe();
    const key = this.data?.key;
    if (!key || !this.data.constituents) return;
    if (document.visibilityState !== 'visible') {  // a background tab doesn't need the moves
      this.pollTimer = setTimeout(() => this.pollLive(), LIVE_POLL_MS);
      return;
    }
    this.pollReq = this.stocks.getIndexLive(key).subscribe({
      next: (res) => {
        this.setLiveMoves(res.live ? res : null);
        this.liveIsFinalSession = res.live && !!res.phase && res.phase !== 'open';
        this.pollTimer = setTimeout(() => this.pollLive(), res.live ? LIVE_POLL_MS : IDLE_POLL_MS);
      },
      error: () => (this.pollTimer = setTimeout(() => this.pollLive(), IDLE_POLL_MS)),
    });
  }

  private setLiveMoves(moves: IndexConstituents | null): void {
    this.liveMoves = moves;
    this.liveRows = new Map((moves?.rows ?? []).map((r) => [r.symbol, r]));
  }

  toggleAll(): void {
    this.showAllConstituents = !this.showAllConstituents;
    this.syncLive();
  }

  /** A member's last price, previous close and day change: its streaming quote, else the latest live
   *  moves, else the bhavcopy's. */
  move(r: IndexConstituent): { price: number | null; prev: number | null; pct: number | null } {
    const q = this.live[r.symbol];
    if (q?.prev_close) return { price: q.price, prev: q.prev_close, pct: q.pct };
    const liveRow = this.liveRows.get(r.symbol);
    const row = liveRow?.pct != null ? liveRow : r;
    const prev = row.close != null && row.change != null ? row.close - row.change : null;
    return { price: row.close, prev, pct: row.pct };
  }

  /** Watch live quotes for the rows on screen only. */
  private syncLive(): void {
    const want = new Set(this.visibleConstituents.slice(0, LIVE_ROWS).map((r) => r.symbol));
    for (const [symbol, sub] of this.liveSubs) {
      if (!want.has(symbol)) {
        sub.unsubscribe();
        this.liveSubs.delete(symbol);
      }
    }
    for (const symbol of want) {
      if (!this.liveSubs.has(symbol)) {
        this.liveSubs.set(symbol, this.stream.watchQuote(symbol).subscribe((q) => (this.live[symbol] = q)));
      }
    }
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
    const o = this.liveMoves ? null : this.data?.overview;  // NSE's count is from page load; live moves are newer
    const c = this.moves;
    const up = o?.advances ?? c?.advances;
    const down = o?.declines ?? c?.declines;
    if (up == null || down == null) return null;
    const flat = o?.unchanged ?? c?.unchanged ?? 0;
    const total = up + down + flat;
    return total ? { up, flat, down, total } : null;
  }

  get topGainers(): IndexConstituent[] {
    return (this.moves?.rows ?? []).filter((r) => (r.pct ?? 0) > 0).slice(0, 5);
  }

  get topLosers(): IndexConstituent[] {
    return (this.moves?.rows ?? []).filter((r) => (r.pct ?? 0) < 0).slice(-5).reverse();
  }

  get visibleConstituents(): IndexConstituent[] {
    const rows = this.data?.constituents?.rows ?? [];
    return this.showAllConstituents ? rows : rows.slice(0, 10);
  }

  /** Widest industry average move, to scale the industry bars. */
  get industryScale(): number {
    return Math.max(0.5, ...(this.moves?.industries ?? []).map((i) => Math.abs(i.avgPct)));
  }

  private formatNumber(value: unknown): string {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '--';
  }
}
