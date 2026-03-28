import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { PortfolioService, PortfolioHolding, SymbolSuggestion } from '../../core/services/portfolio.service';
import { MarketService } from '../../core/services/market.service';
import { LucideAngularModule } from 'lucide-angular';
import { Subject, Subscription, debounceTime, distinctUntilChanged, switchMap } from 'rxjs';

@Component({
  selector: 'app-portfolio',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, LucideAngularModule],
  templateUrl: './portfolio.component.html',
  styleUrl: './portfolio.component.scss'
})
export class PortfolioComponent implements OnInit, OnDestroy {
  readonly allInstrumentTypes: Array<'EQUITY' | 'FUTURE' | 'OPTION'> = ['EQUITY', 'FUTURE', 'OPTION'];
  readonly holdingsViewModes: Array<'both' | 'merged' | 'individual'> = ['both', 'merged', 'individual'];
  loading = true;
  saving = false;
  error = '';
  holdings: PortfolioHolding[] = [];
  totalInvested = 0;
  totalCurrentValue = 0;
  totalPnl = 0;
  totalPnlPct = 0;
  liveCount = 0;
  lastLiveAsOf: number | null = null;
  liveStatus: 'live' | 'partial' | 'stale' = 'stale';
  holdingsViewMode: 'both' | 'merged' | 'individual' = 'both';
  symbolSuggestions: SymbolSuggestion[] = [];
  showSymbolSuggestions = false;
  selectedSuggestion: SymbolSuggestion | null = null;
  lotSize = 1;
  lotLoading = false;
  contractsLoading = false;
  expiryOptions: string[] = [];
  strikeOptions: number[] = [];
  contractsSource: 'dhan' | 'nse' | null = null;
  symbolSearchType: 'derivatives' | 'equity' | 'etf' = 'equity';

  private symbolSearch$ = new Subject<string>();
  private liveRefreshTimer: ReturnType<typeof setInterval> | null = null;
  private liveWsReconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private liveMarketCheckTimer: ReturnType<typeof setInterval> | null = null;
  private liveStreamSub: Subscription | null = null;

  form = {
    symbol: '',
    instrument_type: 'EQUITY' as 'EQUITY' | 'FUTURE' | 'OPTION',
    qty: 1,
    lots: 1,
    avg_price: '',
    expiry: '',
    strike: 0,
    option_type: 'CE' as 'CE' | 'PE',
    action: 'BUY' as 'BUY' | 'SELL',
    notes: ''
  };

  get allowedInstrumentTypes(): Array<'EQUITY' | 'FUTURE' | 'OPTION'> {
    const raw = this.selectedSuggestion?.allowed_instruments;
    if (!raw || raw.length === 0) {
      return this.allInstrumentTypes;
    }
    return raw;
  }

  constructor(
    private portfolioService: PortfolioService,
    private router: Router,
    private marketService: MarketService,
  ) {}

  get isDerivative(): boolean {
    return this.form.instrument_type !== 'EQUITY';
  }

  get showMergedSection(): boolean {
    return this.holdingsViewMode === 'both' || this.holdingsViewMode === 'merged';
  }

  get showIndividualSection(): boolean {
    return this.holdingsViewMode === 'both' || this.holdingsViewMode === 'individual';
  }

  get effectiveQuantity(): number {
    if (this.isDerivative) {
      return Math.max(1, this.form.lots) * Math.max(1, this.lotSize);
    }
    return Math.max(1, this.form.qty);
  }

  get mergedHoldings(): Array<{
    key: string;
    symbol: string;
    instrumentType: 'EQUITY' | 'FUTURE' | 'OPTION';
    totalQty: number;
    totalLots: number;
    avgPrice: number;
    invested: number;
    currentValue: number;
    pnl: number;
    pnlPct: number;
    positions: number;
  }> {
    const grouped = new Map<string, {
      key: string;
      symbol: string;
      instrumentType: 'EQUITY' | 'FUTURE' | 'OPTION';
      totalQty: number;
      totalLots: number;
      invested: number;
      currentValue: number;
      pnl: number;
      positions: number;
    }>();

    for (const holding of this.holdings) {
      const key = this.holdingMergeKey(holding);
      const existing = grouped.get(key);
      const qty = Math.max(0, Number(holding.qty || 0));
      const lots = Math.max(0, Number(holding.lots || 0));
      const invested = Number.isFinite(Number(holding.invested))
        ? Number(holding.invested)
        : Number(holding.avg_price || 0) * qty;
      const currentValue = Number.isFinite(Number(holding.current_value))
        ? Number(holding.current_value)
        : invested;
      const pnl = Number.isFinite(Number(holding.pnl))
        ? Number(holding.pnl)
        : (currentValue - invested);

      if (!existing) {
        grouped.set(key, {
          key,
          symbol: holding.symbol,
          instrumentType: holding.instrument_type,
          totalQty: qty,
          totalLots: lots,
          invested,
          currentValue,
          pnl,
          positions: 1,
        });
        continue;
      }

      existing.totalQty += qty;
      existing.totalLots += lots;
      existing.invested += invested;
      existing.currentValue += currentValue;
      existing.pnl += pnl;
      existing.positions += 1;
    }

    return Array.from(grouped.values())
      .map((item) => ({
        ...item,
        avgPrice: item.totalQty > 0 ? item.invested / item.totalQty : 0,
        pnlPct: item.invested > 0 ? (item.pnl / item.invested) * 100 : 0,
      }))
      .sort((a, b) => a.symbol.localeCompare(b.symbol));
  }

  ngOnInit(): void {
    this.loadHoldings();
    this.syncLiveConnectivity();
    this.liveMarketCheckTimer = setInterval(() => this.syncLiveConnectivity(), 60_000);

    this.symbolSearch$
      .pipe(
        debounceTime(120),
        distinctUntilChanged(),
        switchMap((query) => this.portfolioService.getSymbolSuggestions(query, this.symbolSearchType))
      )
      .subscribe({
        next: (res) => {
          this.symbolSuggestions = res.results || [];
          this.showSymbolSuggestions = this.symbolSuggestions.length > 0;
        },
        error: () => {
          this.symbolSuggestions = [];
          this.showSymbolSuggestions = false;
        }
      });
  }

  ngOnDestroy(): void {
    this.stopLiveStream();
    if (this.liveRefreshTimer) {
      clearInterval(this.liveRefreshTimer);
      this.liveRefreshTimer = null;
    }
    if (this.liveWsReconnectTimer) {
      clearTimeout(this.liveWsReconnectTimer);
      this.liveWsReconnectTimer = null;
    }
    if (this.liveMarketCheckTimer) {
      clearInterval(this.liveMarketCheckTimer);
      this.liveMarketCheckTimer = null;
    }
  }

  private syncLiveConnectivity(): void {
    this.marketService.getSessionStatus().subscribe({
      next: (session) => {
        if (!session?.is_open) {
          this.stopLiveStream();
          this.stopPollingFallback();
          this.liveStatus = 'stale';
          return;
        }
        this.connectLiveStream();
      },
      error: () => {
        // If session check fails, keep existing behavior and avoid interrupting live stream.
        if (!this.liveStreamSub && !this.liveRefreshTimer) {
          this.connectLiveStream();
        }
      },
    });
  }

  private connectLiveStream(): void {
    const token = localStorage.getItem('access_token') || '';
    if (!token) {
      this.startPollingFallback();
      return;
    }

    this.stopLiveStream();
    this.liveStreamSub = this.portfolioService.streamHoldingsLive(token).subscribe({
      next: (snapshot) => {
        this.applyLiveSnapshot(snapshot);
        this.stopPollingFallback();
      },
      error: () => {
        this.startPollingFallback();
        this.scheduleLiveReconnect();
      },
      complete: () => {
        this.startPollingFallback();
        this.scheduleLiveReconnect();
      }
    });
  }

  private scheduleLiveReconnect(): void {
    if (this.liveWsReconnectTimer) {
      clearTimeout(this.liveWsReconnectTimer);
    }
    this.liveWsReconnectTimer = setTimeout(() => {
      this.syncLiveConnectivity();
    }, 2500);
  }

  private stopLiveStream(): void {
    if (this.liveStreamSub) {
      this.liveStreamSub.unsubscribe();
      this.liveStreamSub = null;
    }
  }

  private startPollingFallback(): void {
    if (this.liveRefreshTimer) {
      return;
    }
    this.liveRefreshTimer = setInterval(() => {
      if (!this.isMarketOpenNow()) {
        this.stopPollingFallback();
        this.liveStatus = 'stale';
        return;
      }
      this.loadHoldings(false);
    }, 4000);
  }

  private stopPollingFallback(): void {
    if (this.liveRefreshTimer) {
      clearInterval(this.liveRefreshTimer);
      this.liveRefreshTimer = null;
    }
  }

  private isMarketOpenNow(): boolean {
    const now = new Date();
    const utcMinutes = now.getUTCHours() * 60 + now.getUTCMinutes();
    const istMinutesRaw = utcMinutes + 330;
    const day = now.getUTCDay();

    const adjustedDay = istMinutesRaw >= 1440 ? (day + 1) % 7 : day;
    const adjustedMinutes = istMinutesRaw >= 1440 ? istMinutesRaw - 1440 : istMinutesRaw;

    const isWeekday = adjustedDay >= 1 && adjustedDay <= 5;
    if (!isWeekday) return false;

    const marketOpenMin = 9 * 60 + 15;
    const marketCloseMin = 15 * 60 + 30;
    return adjustedMinutes >= marketOpenMin && adjustedMinutes <= marketCloseMin;
  }

  private applyLiveSnapshot(data: any): void {
    this.holdings = data.holdings || [];
    this.totalInvested = Number(data.total_invested || 0);
    this.totalCurrentValue = Number(data.total_current_value || 0);
    this.totalPnl = Number(data.total_pnl || 0);
    this.totalPnlPct = Number(data.total_pnl_pct || 0);
    this.liveCount = Number(data.live_count || 0);
    this.lastLiveAsOf = Number(data.as_of || 0);
    this.liveStatus = this.liveCount === 0
      ? 'stale'
      : (this.liveCount === this.holdings.length ? 'live' : 'partial');
    this.error = '';
    this.loading = false;
  }

  onSymbolInput(value: string): void {
    const query = value.trim();
    this.form.symbol = value;

    // Reset constraint if user edits symbol manually.
    if (!this.selectedSuggestion || this.selectedSuggestion.symbol !== value.trim().toUpperCase()) {
      this.selectedSuggestion = null;
      if (this.isDerivative) {
        this.loadLotSize(value.trim());
        if (query.length >= 2) {
          this.loadDerivativeContracts(value.trim(), this.form.instrument_type === 'OPTION' ? this.form.expiry : undefined);
        }
      }
    }

    if (query.length < 2) {
      this.symbolSuggestions = [];
      this.showSymbolSuggestions = false;
      return;
    }

    this.symbolSearch$.next(query);
  }

  selectSuggestion(item: SymbolSuggestion): void {
    this.form.symbol = item.symbol;
    this.selectedSuggestion = item;
    if (item.allowed_instruments && item.allowed_instruments.length > 0) {
      if (!item.allowed_instruments.includes(this.form.instrument_type)) {
        this.form.instrument_type = item.allowed_instruments[0];
      }
    }
    this.loadLotSize(item.symbol);
    if (this.form.instrument_type !== 'EQUITY') {
      this.loadDerivativeContracts(item.symbol);
    }
    this.showSymbolSuggestions = false;
  }

  onInstrumentTypeChange(): void {
    if (this.isDerivative) {
      this.loadLotSize(this.form.symbol.trim());
      this.loadDerivativeContracts(this.form.symbol.trim());
    } else {
      this.expiryOptions = [];
      this.strikeOptions = [];
      this.contractsSource = null;
    }
  }

  onSearchTypeChange(): void {
    this.selectedSuggestion = null;
    this.symbolSuggestions = [];
    this.showSymbolSuggestions = false;

    const query = this.form.symbol.trim();
    if (query.length >= 2) {
      this.symbolSearch$.next(query);
    }
  }

  onExpiryChange(): void {
    if (this.form.instrument_type !== 'EQUITY' && this.form.symbol.trim()) {
      this.loadDerivativeContracts(this.form.symbol.trim(), this.form.expiry);
    }
  }

  private loadLotSize(symbol: string): void {
    if (!symbol) {
      this.lotSize = 1;
      return;
    }

    this.lotLoading = true;
    this.portfolioService.getLotSize(symbol.toUpperCase()).subscribe({
      next: (res) => {
        this.lotSize = Math.max(1, Number(res?.lot_size || 1));
        this.lotLoading = false;
      },
      error: () => {
        this.lotSize = 1;
        this.lotLoading = false;
      }
    });
  }

  private loadDerivativeContracts(symbol: string, expiry?: string): void {
    const cleanSymbol = symbol.trim().toUpperCase();
    if (!cleanSymbol || this.form.instrument_type === 'EQUITY') {
      return;
    }

    const instrumentType = this.form.instrument_type as 'FUTURE' | 'OPTION';
    this.contractsLoading = true;
    this.portfolioService.getDerivativeContracts(cleanSymbol, instrumentType, expiry).subscribe({
      next: (res) => {
        this.expiryOptions = Array.isArray(res.expiries) ? res.expiries : [];
        this.contractsSource = res.source;

        const selectedExpiry = expiry && this.expiryOptions.includes(expiry)
          ? expiry
          : (res.selected_expiry || this.expiryOptions[0] || '');
        this.form.expiry = selectedExpiry;

        if (this.form.instrument_type === 'OPTION') {
          this.strikeOptions = (Array.isArray(res.strikes) ? res.strikes : []).sort((a, b) => a - b);
          const strikeExists = this.strikeOptions.some((s) => Number(s) === Number(this.form.strike));
          if (!strikeExists) {
            this.form.strike = this.strikeOptions.length > 0 ? this.strikeOptions[0] : 0;
          }
        } else {
          this.strikeOptions = [];
          this.form.strike = 0;
        }

        this.contractsLoading = false;
      },
      error: () => {
        this.expiryOptions = [];
        this.strikeOptions = [];
        this.contractsSource = null;
        this.contractsLoading = false;
      }
    });
  }

  hideSuggestionsWithDelay(): void {
    setTimeout(() => {
      this.showSymbolSuggestions = false;
    }, 150);
  }

  loadHoldings(showLoading = true): void {
    if (showLoading) {
      this.loading = true;
    }
    this.error = '';
    this.portfolioService.getHoldingsLive().subscribe({
      next: (data) => {
        this.applyLiveSnapshot(data);
      },
      error: (err) => {
        this.portfolioService.getHoldings().subscribe({
          next: (fallback) => {
            this.holdings = fallback.holdings;
            this.totalInvested = fallback.total_invested;
            this.totalCurrentValue = fallback.total_invested;
            this.totalPnl = 0;
            this.totalPnlPct = 0;
            this.liveCount = 0;
            this.lastLiveAsOf = null;
            this.liveStatus = 'stale';
            this.loading = false;
          },
          error: () => {
            this.loading = false;
            this.error = err?.error?.detail || 'Unable to fetch holdings right now.';
          }
        });
      }
    });
  }

  addHolding(): void {
    const avgPrice = Number(this.form.avg_price);

    if (!this.allowedInstrumentTypes.includes(this.form.instrument_type)) {
      this.error = `Instrument type ${this.form.instrument_type} is not allowed for this symbol series.`;
      return;
    }

    const requestedQty = this.isDerivative ? this.effectiveQuantity : this.form.qty;
    if (!this.form.symbol.trim() || requestedQty <= 0 || !Number.isFinite(avgPrice) || avgPrice <= 0) {
      this.error = 'Please enter a valid symbol, quantity and average price.';
      return;
    }

    if (this.isDerivative && !this.form.expiry) {
      this.error = 'Please select an expiry date.';
      return;
    }

    if (this.form.instrument_type === 'OPTION') {
      const validStrike = Number(this.form.strike);
      if (!Number.isFinite(validStrike) || validStrike <= 0) {
        this.error = 'Please select a valid strike.';
        return;
      }
    }

    this.saving = true;
    this.error = '';

    const payload: any = {
      symbol: this.form.symbol.trim().toUpperCase(),
      instrument_type: this.form.instrument_type,
      qty: requestedQty,
      avg_price: avgPrice,
      notes: this.form.notes || undefined,
    };

    if (this.form.instrument_type !== 'EQUITY') {
      payload.lots = this.form.lots;
      payload.expiry = this.form.expiry || undefined;
      payload.strike = this.form.instrument_type === 'OPTION' ? (this.form.strike || undefined) : undefined;
      payload.option_type = this.form.instrument_type === 'OPTION' ? this.form.option_type : undefined;
      payload.action = this.form.action;
    }

    this.portfolioService.addHolding(payload).subscribe({
      next: () => {
        this.saving = false;
        this.resetForm();
        this.loadHoldings();
      },
      error: (err) => {
        this.saving = false;
        this.error = err?.error?.detail || 'Unable to add holding right now.';
      }
    });
  }

  removeHolding(holdingId: number): void {
    this.portfolioService.deleteHolding(holdingId).subscribe({
      next: () => this.loadHoldings(),
      error: (err) => {
        this.error = err?.error?.detail || 'Unable to delete holding right now.';
      }
    });
  }

  openHoldingChart(symbol: string): void {
    const normalized = (symbol || '').trim().split(/\s+/)[0]?.toUpperCase();
    if (!normalized) {
      return;
    }
    this.router.navigate(['/stocks', normalized]);
  }

  private holdingMergeKey(holding: PortfolioHolding): string {
    const symbol = (holding.symbol || '').trim().toUpperCase();
    const instrument = holding.instrument_type;

    if (instrument === 'EQUITY') {
      return `${symbol}|${instrument}`;
    }

    const expiry = (holding.expiry || '').trim().toUpperCase();
    const strike = holding.strike != null ? Number(holding.strike).toFixed(2) : 'NA';
    const optionType = (holding.option_type || '').trim().toUpperCase();
    const action = (holding.action || '').trim().toUpperCase();
    return `${symbol}|${instrument}|${expiry}|${strike}|${optionType}|${action}`;
  }

  private resetForm(): void {
    this.form = {
      symbol: '',
      instrument_type: 'EQUITY',
      qty: 1,
      lots: 1,
      avg_price: '',
      expiry: '',
      strike: 0,
      option_type: 'CE',
      action: 'BUY',
      notes: ''
    };
    this.selectedSuggestion = null;
    this.lotSize = 1;
    this.expiryOptions = [];
    this.strikeOptions = [];
    this.contractsSource = null;
  }
}
