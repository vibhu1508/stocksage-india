import { AfterViewInit, Component, ElementRef, OnDestroy, QueryList, ViewChildren } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { LucideAngularModule } from 'lucide-angular';
import { Subscription, interval, startWith, switchMap } from 'rxjs';

import { AuthService, User } from '../../core/services/auth.service';
import { ThemeService } from '../../core/services/theme.service';
import { MarketService } from '../../core/services/market.service';

interface LandingFeature {
  icon: string;
  title: string;
  blurb: string;
  /** Short one-line highlight shown on the feature card. */
  cue: string;
}

interface TickerItem {
  symbol: string;
  value: string;
  change: string;
  up: boolean;
}

@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [CommonModule, LucideAngularModule],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.scss',
})
export class LandingComponent implements AfterViewInit, OnDestroy {
  /** Index of the feature the avatar is currently pointing at (drives the stage). */
  activeFeature = 0;

  // Live index strip — populated from the backend /api/market/indices endpoint.
  // These placeholders show only until the first live response arrives.
  ticker: TickerItem[] = [
    { symbol: 'SENSEX', value: '—', change: '', up: false },
    { symbol: 'NIFTY 50', value: '—', change: '', up: false },
    { symbol: 'BANKNIFTY', value: '—', change: '', up: false },
    { symbol: 'FINNIFTY', value: '—', change: '', up: false },
    { symbol: 'NIFTY IT', value: '—', change: '', up: false },
  ];

  readonly features: LandingFeature[] = [
    {
      icon: 'candlestick-chart',
      title: 'Live & historical charts',
      blurb: 'Real-time candles streamed from the exchange feed, plus any custom date range and interval — even when the market is closed.',
      cue: 'Pick any date range you want.',
    },
    {
      icon: 'line-chart',
      title: 'F&O analytics',
      blurb: 'Futures & options built-up, open-interest flow, and Nifty-wide gainers and losers computed from live derivative data.',
      cue: 'Follow the smart money.',
    },
    {
      icon: 'layers',
      title: 'Strategy builder',
      blurb: 'Assemble multi-leg option strategies and see payoff, breakeven, and Greeks before you ever place a trade.',
      cue: 'Model the trade first.',
    },
    {
      icon: 'briefcase',
      title: 'Portfolio tracking',
      blurb: 'Track equity and derivative holdings with live P&L that ticks in real time through the trading session.',
      cue: 'Your P&L, live.',
    },
    {
      icon: 'megaphone',
      title: 'Corporate filings',
      blurb: 'NSE and BSE announcements for every symbol, so you never miss a result, dividend, or board meeting.',
      cue: 'Never miss a filing.',
    },
    {
      icon: 'graduation-cap',
      title: 'Learn as you go',
      blurb: 'A curated video library that turns market concepts into something you can actually act on.',
      cue: 'Level up your edge.',
    },
  ];

  @ViewChildren('reveal') private revealEls!: QueryList<ElementRef<HTMLElement>>;
  @ViewChildren('featureRow') private featureRows!: QueryList<ElementRef<HTMLElement>>;

  private revealObserver?: IntersectionObserver;
  private featureObserver?: IntersectionObserver;
  private tickerSub?: Subscription;

  /** Signed-in user object (for the name) — may lag behind the token on a fresh load. */
  readonly currentUser$;

  constructor(
    private authService: AuthService,
    public themeService: ThemeService,
    private marketService: MarketService,
    private router: Router,
  ) {
    this.currentUser$ = this.authService.currentUser$;
  }

  /**
   * Synchronous auth check driving the "Go to Dashboard" vs "Log in / Sign up" CTAs.
   * Uses the stored token (not the async /me result) so the correct CTA shows on the
   * very first render, even before the user profile has finished loading.
   */
  get isLoggedIn(): boolean {
    return this.authService.isAuthenticated();
  }

  ngAfterViewInit(): void {
    // Fade/slide elements in as they scroll into view.
    this.revealObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            this.revealObserver?.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -8% 0px' },
    );
    this.revealEls?.forEach((el) => this.revealObserver!.observe(el.nativeElement));

    // Track which feature is centred so the avatar can point at it.
    this.featureObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const idx = Number((entry.target as HTMLElement).dataset['index']);
            if (Number.isFinite(idx)) {
              this.activeFeature = idx;
            }
          }
        }
      },
      { threshold: 0.55 },
    );
    this.featureRows?.forEach((el) => this.featureObserver!.observe(el.nativeElement));

    // Live index ticker: refresh every 30s (keeps placeholders on empty responses).
    this.tickerSub = interval(30_000)
      .pipe(
        startWith(0),
        switchMap(() => this.marketService.getIndices()),
      )
      .subscribe((res) => {
        const indices = res?.indices ?? [];
        if (indices.length === 0) return;
        this.ticker = indices.map((i) => ({
          symbol: i.symbol,
          value: this.marketService.formatIndian(i.value),
          change: `${i.pct_change >= 0 ? '+' : ''}${i.pct_change.toFixed(2)}%`,
          up: i.up,
        }));
      });
  }

  ngOnDestroy(): void {
    this.revealObserver?.disconnect();
    this.featureObserver?.disconnect();
    this.tickerSub?.unsubscribe();
  }

  /** Both "Log in" and "Sign up" flow through Google OAuth (first-time users are created + onboarded). */
  continueWithGoogle(): void {
    this.authService.loginWithGoogle();
  }

  /** Signed-in visitors jump straight into the app. */
  goToDashboard(): void {
    this.router.navigate(['/dashboard']);
  }

  toggleTheme(): void {
    this.themeService.toggleTheme();
  }



}
