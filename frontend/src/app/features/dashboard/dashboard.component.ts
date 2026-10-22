import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { trigger, transition, style, animate } from '@angular/animations';
import { Subscription } from 'rxjs';
import { AuthService, User } from '../../core/services/auth.service';
import { MarketService, MarketData, StockMover } from '../../core/services/market.service';
import { LucideAngularModule } from 'lucide-angular';
import { LiveQuote, MarketStreamService } from '../../core/services/market-stream.service';
import { FlashDirective } from '../../shared/directives/flash.directive';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink, LucideAngularModule, FlashDirective],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
  animations: [
    trigger('slideUp', [
      transition(':enter', [
        style({ opacity: 0, transform: 'translateY(15px)' }),
        animate('350ms ease-out', style({ opacity: 1, transform: 'translateY(0)' }))
      ]),
      transition(':leave', [
        animate('200ms ease-in', style({ opacity: 0, transform: 'translateY(-10px)' }))
      ])
    ])
  ]
})
export class DashboardComponent implements OnInit, OnDestroy {
  user: User | null = null;
  greeting = '';
  marketData: MarketData | null = null;
  marketLoading = true;

  private marketSub?: Subscription;

  // Top gainers/losers carousel
  topGainers: StockMover[] = [];
  topLosers: StockMover[] = [];
  gainerIndex = 0;
  loserIndex = 0;
  private gainerTimer?: any;
  private loserTimer?: any;
  private moversTimer?: any;

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
    private marketStream: MarketStreamService
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

    this.gainerTimer = setInterval(() => {
      if (this.topGainers.length) this.gainerIndex = (this.gainerIndex + 1) % this.topGainers.length;
    }, 3000);
    this.loserTimer = setInterval(() => {
      if (this.topLosers.length) this.loserIndex = (this.loserIndex + 1) % this.topLosers.length;
    }, 3000);
    this.loadMovers();
    // The ranking is an NSE snapshot (refreshed each minute); prices on screen stream live.
    this.moversTimer = setInterval(() => this.loadMovers(), 60_000);
  }

  private loadMovers(): void {
    this.marketService.getTopGainers().subscribe(data => {
      this.topGainers = data.gainers || [];
      this.gainerIndex = Math.min(this.gainerIndex, Math.max(0, this.topGainers.length - 1));
      this.watchMovers();
    });
    this.marketService.getTopLosers().subscribe(data => {
      this.topLosers = data.losers || [];
      this.loserIndex = Math.min(this.loserIndex, Math.max(0, this.topLosers.length - 1));
      this.watchMovers();
    });
  }

  /** Keep one live quote per mover on screen; drop the ones that left the lists. */
  private watchMovers(): void {
    const wanted = new Set([...this.topGainers, ...this.topLosers].map(m => m.symbol));
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

  moverPrice(m: StockMover): number {
    return this.liveMovers.get(m.symbol)?.price ?? m.price;
  }

  moverPct(m: StockMover): number {
    return this.liveMovers.get(m.symbol)?.pct ?? m.pct_change;
  }

  moverChange(m: StockMover): number {
    return this.liveMovers.get(m.symbol)?.change ?? m.change;
  }

  ngOnDestroy(): void {
    this.marketSub?.unsubscribe();
    if (this.gainerTimer) clearInterval(this.gainerTimer);
    if (this.loserTimer) clearInterval(this.loserTimer);
    if (this.moversTimer) clearInterval(this.moversTimer);
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

  get currentGainer(): StockMover | null {
    return this.topGainers.length > 0 ? this.topGainers[this.gainerIndex] : null;
  }

  get currentLoser(): StockMover | null {
    return this.topLosers.length > 0 ? this.topLosers[this.loserIndex] : null;
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
        route: null as string | null,
        changePositive: this.niftyPositive,
        raw: this.liveNifty?.price ?? null
      },
      {
        label: 'SENSEX',
        value: this.sensexValue,
        icon: this.sensexPositive ? 'trending-up' : 'trending-down',
        iconClass: this.sensexPositive ? 'text-green-500' : 'text-red-500',
        change: this.sensexChange || null,
        route: null as string | null,
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
