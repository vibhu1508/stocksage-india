import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PortfolioService, PortfolioHolding, SymbolSuggestion } from '../../core/services/portfolio.service';
import { LucideAngularModule } from 'lucide-angular';
import { Subject, debounceTime, distinctUntilChanged, switchMap } from 'rxjs';

@Component({
  selector: 'app-portfolio',
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule],
  templateUrl: './portfolio.component.html',
  styleUrl: './portfolio.component.scss'
})
export class PortfolioComponent implements OnInit {
  readonly allInstrumentTypes: Array<'EQUITY' | 'FUTURE' | 'OPTION'> = ['EQUITY', 'FUTURE', 'OPTION'];
  loading = true;
  saving = false;
  error = '';
  holdings: PortfolioHolding[] = [];
  totalInvested = 0;
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

  constructor(private portfolioService: PortfolioService) {}

  get isDerivative(): boolean {
    return this.form.instrument_type !== 'EQUITY';
  }

  get effectiveQuantity(): number {
    if (this.isDerivative) {
      return Math.max(1, this.form.lots) * Math.max(1, this.lotSize);
    }
    return Math.max(1, this.form.qty);
  }

  ngOnInit(): void {
    this.loadHoldings();
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

  loadHoldings(): void {
    this.loading = true;
    this.error = '';
    this.portfolioService.getHoldings().subscribe({
      next: (data) => {
        this.holdings = data.holdings;
        this.totalInvested = data.total_invested;
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.detail || 'Unable to fetch holdings right now.';
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
