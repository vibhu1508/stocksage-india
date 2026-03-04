import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { trigger, transition, style, animate } from '@angular/animations';
import { Subscription } from 'rxjs';
import { AuthService, User } from '../../core/services/auth.service';
import { MarketService, MarketData, StockMover } from '../../core/services/market.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink],
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
  currentTime = new Date();
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

  quickActions = [
    { label: 'Compare Stocks', description: 'Analyze price changes between dates', icon: '📊', route: '/stocks' },
    { label: 'F&O Analysis', description: 'View futures and options data', icon: '📈', route: '/fo' },
    { label: 'NSE Announcements', description: 'Latest corporate filings', icon: '📰', route: '/announcements' },
    { label: 'Learn', description: 'Videos by Girish Gupta', icon: '🎓', route: '/learn' }
  ];

  constructor(
    private authService: AuthService,
    private marketService: MarketService
  ) { }

  ngOnInit(): void {
    this.authService.currentUser$.subscribe(user => {
      this.user = user;
    });

    this.setGreeting();

    setInterval(() => {
      this.currentTime = new Date();
    }, 1000);

    this.marketSub = this.marketService.getLiveDataStream(10000).subscribe(data => {
      this.marketData = data;
      this.marketLoading = false;
    });

    this.marketService.getTopGainers().subscribe(data => {
      this.topGainers = data.gainers || [];
      if (this.topGainers.length > 0) {
        this.gainerTimer = setInterval(() => {
          this.gainerIndex = (this.gainerIndex + 1) % this.topGainers.length;
        }, 3000);
      }
    });
    this.marketService.getTopLosers().subscribe(data => {
      this.topLosers = data.losers || [];
      if (this.topLosers.length > 0) {
        this.loserTimer = setInterval(() => {
          this.loserIndex = (this.loserIndex + 1) % this.topLosers.length;
        }, 3000);
      }
    });
  }

  ngOnDestroy(): void {
    this.marketSub?.unsubscribe();
    if (this.gainerTimer) clearInterval(this.gainerTimer);
    if (this.loserTimer) clearInterval(this.loserTimer);
  }

  private setGreeting(): void {
    const hour = this.currentTime.getHours();
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
    if (!this.marketData?.nifty) return '--';
    return this.marketService.formatIndian(this.marketData.nifty.value);
  }

  get niftyChange(): string {
    if (!this.marketData?.nifty) return '';
    const pct = this.marketData.nifty.pct_change;
    const num = parseFloat(pct);
    return (num >= 0 ? '+' : '') + pct + '%';
  }

  get niftyPositive(): boolean {
    if (!this.marketData?.nifty) return true;
    return parseFloat(this.marketData.nifty.pct_change) >= 0;
  }

  get sensexValue(): string {
    if (!this.marketData?.sensex) return '--';
    return this.marketService.formatIndian(this.marketData.sensex.value);
  }

  get sensexChange(): string {
    if (!this.marketData?.sensex) return '';
    const pct = this.marketData.sensex.pct_change;
    const num = parseFloat(pct);
    return (num >= 0 ? '+' : '') + pct + '%';
  }

  get sensexPositive(): boolean {
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
        icon: this.marketStatus === 'Open' ? '🟢' : this.marketStatus === 'Closed' ? '🔴' : '🟡',
        change: null as string | null,
        changePositive: true
      },
      {
        label: 'NIFTY 50',
        value: this.niftyValue,
        icon: this.niftyPositive ? '📈' : '📉',
        change: this.niftyChange || null,
        changePositive: this.niftyPositive
      },
      {
        label: 'SENSEX',
        value: this.sensexValue,
        icon: this.sensexPositive ? '📈' : '📉',
        change: this.sensexChange || null,
        changePositive: this.sensexPositive
      },
      {
        label: 'My Portfolio',
        value: 'View',
        icon: '💼',
        change: 'Coming Soon' as string | null,
        changePositive: true
      }
    ];
  }
}
