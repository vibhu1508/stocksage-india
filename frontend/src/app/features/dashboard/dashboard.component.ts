import { Component, ElementRef, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Subscription, finalize } from 'rxjs';
import { AuthService, User } from '../../core/services/auth.service';
import { MarketPhase, MarketService, MarketData, StockMover } from '../../core/services/market.service';
import { LucideAngularModule } from 'lucide-angular';
import { LiveQuote, MarketStreamService } from '../../core/services/market-stream.service';
import { FlashDirective } from '../../shared/directives/flash.directive';
import { CompanyLogoComponent } from '../../shared/components/company-logo/company-logo.component';
import { ShortNamePipe } from '../../shared/pipes/short-name.pipe';

const MOVERS_GROUP_KEY = 'stocksage.moversGroup';

function readMoversGroup(): string {
  try { return localStorage.getItem(MOVERS_GROUP_KEY) || 'NIFTY'; } catch { return 'NIFTY'; }
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink, LucideAngularModule, FlashDirective, CompanyLogoComponent, ShortNamePipe],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit, OnDestroy {
  user: User | null = null;
  greeting = '';
  marketData: MarketData | null = null;
  marketLoading = true;

  private marketSub?: Subscription;

  // Top gainers/losers of one NSE group, as NSE publishes them; re-ranked every 20 s while the market
  // is in session (the server refreshes NSE's lists as often), every minute otherwise.
  topGainers: StockMover[] = [];
  topLosers: StockMover[] = [];
  moversGroup = readMoversGroup();
  moversGroups: Array<{ key: string; label: string }> = [{ key: 'NIFTY', label: 'NIFTY 50' }];
  moversPhase: MarketPhase = 'closed';
  moversAsOf: string | null = null;
  moversLoading = false;
  moversUpdatedAt: Date | null = null;
  sparkShapes: Record<string, { line: string; base: number }> = {};
  private sparks: Record<string, number[]> = {};
  private sparksAt = 0;
  private moversTimer?: ReturnType<typeof setTimeout>;
  private moversReq?: Subscription;

  // Live quotes from the Dhan feed (market service): indices and the movers on screen.
  liveNifty: LiveQuote | null = null;
  liveSensex: LiveQuote | null = null;
  private readonly liveMovers = new Map<string, LiveQuote>();
  private readonly moverSubs = new Map<string, Subscription>();
  private readonly liveSubs = new Subscription();

  quickActions = [
    { label: 'Watchlist', description: 'Track symbols with chart and market depth', icon: 'bar-chart-2', route: '/stocks' },
    { label: 'After Market Analysis', description: 'F&O, stock comparison, and moving averages', icon: 'line-chart', route: '/after-market-analysis' },
    { label: 'Strategy Builder', description: 'Build and analyze option strategies', icon: 'pencil-ruler', route: '/strategy-builder' },
    { label: 'NSE Announcements', description: 'Latest corporate filings', icon: 'megaphone', route: '/announcements' },
    { label: 'Learn', description: 'Videos by Girish Gupta', icon: 'graduation-cap', route: '/learn' }
  ];

  constructor(
    private authService: AuthService,
    private marketService: MarketService,
    private marketStream: MarketStreamService,
    private host: ElementRef<HTMLElement>
  ) { }

  ngOnInit(): void {
    this.authService.currentUser$.subscribe(user => {
      this.user = user;
    });

    this.setGreeting();

    this.marketSub = this.marketService.getLiveDataStream(10000).subscribe(data => {
      this.marketData = data;
      this.marketLoading = false;
    });

    this.liveSubs.add(this.marketStream.watchQuote('NIFTY').subscribe(q => (this.liveNifty = q)));
    this.liveSubs.add(this.marketStream.watchQuote('SENSEX').subscribe(q => (this.liveSensex = q)));

    this.loadMovers();
  }

  loadMovers(): void {
    clearTimeout(this.moversTimer);
    this.moversReq?.unsubscribe();
    this.moversLoading = true;
    const group = this.moversGroup;
    this.moversReq = this.marketService.getMovers(group).pipe(finalize(() => (this.moversLoading = false))).subscribe({
      next: (res) => {
        if (group !== this.moversGroup) return;
        if (res.group !== group) {  // a retired group was remembered: the server sent NIFTY 50
          this.moversGroup = res.group;
          try { localStorage.setItem(MOVERS_GROUP_KEY, res.group); } catch { /* private mode */ }
        }
        this.topGainers = res.gainers;
        this.topLosers = res.losers;
        const firstLoad = this.moversGroups.length < res.groups.length;
        this.moversGroups = res.groups;
        if (firstLoad) setTimeout(() => this.revealActiveChip());
        this.moversPhase = res.phase;
        this.moversAsOf = res.asOf;
        this.moversUpdatedAt = new Date();
        this.watchMovers();
        this.loadSparklines();
        this.scheduleMovers();
      },
      error: () => this.scheduleMovers(),  // keep the last lists on screen
    });
  }

  setMoversGroup(group: string): void {
    if (group === this.moversGroup) return;
    this.moversGroup = group;
    try { localStorage.setItem(MOVERS_GROUP_KEY, group); } catch { /* private mode: not remembered */ }
    this.topGainers = [];  // never show the previous group's stocks under the new group's name
    this.topLosers = [];
    this.loadMovers();
  }

  /** On phones the chips scroll sideways: bring a remembered group's chip into view. */
  private revealActiveChip(): void {
    this.host.nativeElement.querySelector('.group-chips [aria-checked="true"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }

  get moversLabel(): string {
    return this.moversGroups.find(g => g.key === this.moversGroup)?.label ?? this.moversGroup;
  }

  private scheduleMovers(): void {
    clearTimeout(this.moversTimer);
    const wait = this.moversPhase === 'closed' ? 60_000 : 20_000;
    this.moversTimer = setTimeout(() => (document.visibilityState === 'visible' ? this.loadMovers() : this.scheduleMovers()), wait);
  }

  /** Sparklines for the stocks on screen: new ones at once, the rest about once a minute in session. */
  private loadSparklines(): void {
    const symbols = [...this.topGainers, ...this.topLosers].map(m => m.symbol);
    const refreshAll = this.moversPhase !== 'closed' && Date.now() - this.sparksAt > 60_000;
    const wanted = refreshAll ? symbols : symbols.filter(s => !(s in this.sparks));
    this.buildSparkShapes();
    if (!wanted.length) return;
    if (refreshAll) this.sparksAt = Date.now();
    this.marketService.getSparklines(wanted).subscribe({
      next: (res) => {
        this.sparks = { ...this.sparks, ...res.sparklines };
        this.buildSparkShapes();
      },
      error: () => {},
    });
  }

  /** SVG polyline points (viewBox 100 x 30) per stock, with the previous close as a dashed baseline. */
  private buildSparkShapes(): void {
    const shapes: Record<string, { line: string; base: number }> = {};
    for (const m of [...this.topGainers, ...this.topLosers]) {
      const points = this.sparks[m.symbol];
      if (!points || points.length < 2) continue;
      const prev = m.prev_close || points[0];
      const lo = Math.min(prev, ...points);
      const span = Math.max(Math.max(prev, ...points) - lo, 1e-9);
      const y = (v: number) => +(28 - ((v - lo) / span) * 26).toFixed(2);
      shapes[m.symbol] = {
        line: points.map((v, i) => `${+(i / (points.length - 1) * 100).toFixed(2)},${y(v)}`).join(' '),
        base: y(prev),
      };
    }
    this.sparkShapes = shapes;
  }

  /** Keep one live quote per mover on screen while the market is open; drop the rest. After 15:30
   *  NSE's official close (a VWAP) is the right number, not the last trade. */
  private watchMovers(): void {
    const wanted = new Set(this.moversPhase === 'open' ? [...this.topGainers, ...this.topLosers].map(m => m.symbol) : []);
    for (const [symbol, sub] of this.moverSubs) {
      if (!wanted.has(symbol)) {
        sub.unsubscribe();
        this.moverSubs.delete(symbol);
        this.liveMovers.delete(symbol);
      }
    }
    for (const symbol of wanted) {
      if (!this.moverSubs.has(symbol)) {
        this.moverSubs.set(symbol, this.marketStream.watchQuote(symbol).subscribe(q => this.liveMovers.set(symbol, q)));
      }
    }
  }

  /** NSE's value, or while the market is open the live price, measured against NSE's previous close
   *  (adjusted on corporate-action days, unlike a stored close). */
  moverPrice(m: StockMover): number {
    return this.liveMovers.get(m.symbol)?.price ?? m.price;
  }

  moverChange(m: StockMover): number {
    const live = this.liveMovers.get(m.symbol);
    return live && m.prev_close ? live.price - m.prev_close : m.change;
  }

  moverPct(m: StockMover): number {
    const live = this.liveMovers.get(m.symbol);
    return live && m.prev_close ? ((live.price - m.prev_close) / m.prev_close) * 100 : m.pct_change;
  }

  ngOnDestroy(): void {
    this.marketSub?.unsubscribe();
    clearTimeout(this.moversTimer);
    this.moversReq?.unsubscribe();
    this.liveSubs.unsubscribe();
    this.moverSubs.forEach(sub => sub.unsubscribe());
  }

  private setGreeting(): void {
    const hour = new Date().getHours();
    if (hour < 12) {
      this.greeting = 'Good Morning';
    } else if (hour < 17) {
      this.greeting = 'Good Afternoon';
    } else {
      this.greeting = 'Good Evening';
    }
  }

  get marketStatus(): string {
    return this.marketData?.market_status ?? 'Loading...';
  }

  get marketStatusClass(): string {
    switch (this.marketStatus) {
      case 'Open': return 'status-open';
      case 'Pre-Open':
      case 'Pre-Market': return 'status-preopen';
      case 'Closed': return 'status-closed';
      default: return '';
    }
  }

  get niftyValue(): string {
    if (this.liveNifty) return this.marketService.formatIndian(this.liveNifty.price);
    if (!this.marketData?.nifty) return '--';
    return this.marketService.formatIndian(this.marketData.nifty.value);
  }

  get niftyChange(): string {
    if (this.liveNifty?.pct != null) return (this.liveNifty.pct >= 0 ? '+' : '') + this.liveNifty.pct.toFixed(2) + '%';
    if (!this.marketData?.nifty) return '';
    const pct = this.marketData.nifty.pct_change;
    const num = parseFloat(pct);
    return (num >= 0 ? '+' : '') + pct + '%';
  }

  get niftyPositive(): boolean {
    if (this.liveNifty?.pct != null) return this.liveNifty.pct >= 0;
    if (!this.marketData?.nifty) return true;
    return parseFloat(this.marketData.nifty.pct_change) >= 0;
  }

  get sensexValue(): string {
    if (this.liveSensex) return this.marketService.formatIndian(this.liveSensex.price);
    if (!this.marketData?.sensex) return '--';
    return this.marketService.formatIndian(this.marketData.sensex.value);
  }

  get sensexChange(): string {
    if (this.liveSensex?.pct != null) return (this.liveSensex.pct >= 0 ? '+' : '') + this.liveSensex.pct.toFixed(2) + '%';
    if (!this.marketData?.sensex) return '';
    const pct = this.marketData.sensex.pct_change;
    const num = parseFloat(pct);
    return (num >= 0 ? '+' : '') + pct + '%';
  }

  get sensexPositive(): boolean {
    if (this.liveSensex?.pct != null) return this.liveSensex.pct >= 0;
    if (!this.marketData?.sensex) return true;
    return parseFloat(this.marketData.sensex.pct_change) >= 0;
  }

  get moverCards() {
    return [
      { kind: 'gainers' as const, title: 'Top Gainers', icon: 'arrow-up-right', up: true, rows: this.topGainers },
      { kind: 'losers' as const, title: 'Top Losers', icon: 'arrow-down-right', up: false, rows: this.topLosers },
    ];
  }

  /** 12,34,567 shares -> "12.3L"; Indian lakh/crore units. */
  compactVolume(volume: number): string {
    const v = Number(volume) || 0;
    if (v >= 1e7) return `${(v / 1e7).toFixed(1)}Cr`;
    if (v >= 1e5) return `${(v / 1e5).toFixed(1)}L`;
    if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
    return String(v);
  }

  get stats() {
    return [
      {
        label: 'Market Status',
        value: this.marketStatus,
        icon: this.marketStatus === 'Open' ? 'check-circle-2' : this.marketStatus === 'Closed' ? 'x-circle' : 'alert-circle',
        iconClass: this.marketStatus === 'Open' ? 'text-green-500' : this.marketStatus === 'Closed' ? 'text-red-500' : 'text-yellow-500',
        change: null as string | null,
        route: null as string | null,
        changePositive: true,
        raw: null as number | null
      },
      {
        label: 'NIFTY 50',
        value: this.niftyValue,
        icon: this.niftyPositive ? 'trending-up' : 'trending-down',
        iconClass: this.niftyPositive ? 'text-green-500' : 'text-red-500',
        change: this.niftyChange || null,
        route: '/stocks/INDEX:NIFTY' as string | null,
        changePositive: this.niftyPositive,
        raw: this.liveNifty?.price ?? null
      },
      {
        label: 'SENSEX',
        value: this.sensexValue,
        icon: this.sensexPositive ? 'trending-up' : 'trending-down',
        iconClass: this.sensexPositive ? 'text-green-500' : 'text-red-500',
        change: this.sensexChange || null,
        route: '/stocks/INDEX:SENSEX' as string | null,
        changePositive: this.sensexPositive,
        raw: this.liveSensex?.price ?? null
      },
      {
        label: 'My Portfolio',
        value: 'View',
        icon: 'briefcase',
        iconClass: 'text-primary',
        change: 'Manage Holdings' as string | null,
        route: '/portfolio',
        changePositive: true,
        raw: null as number | null
      }
    ];
  }
}
