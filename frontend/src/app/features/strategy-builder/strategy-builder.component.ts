import { Component, OnInit, OnDestroy, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { trigger, state, style, transition, animate } from '@angular/animations';
import { FormsModule } from '@angular/forms';
import { StrategyService, Position, Strategy, UserStrategies, PortfolioSyncedHolding } from '../../core/services/strategy.service';
import { Chart, registerables } from 'chart.js';
import { LucideAngularModule } from 'lucide-angular';
import { Subject, forkJoin } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

Chart.register(...registerables);

const STRATEGY_PRESETS = [
  // ===== BULLISH =====
  { name: 'Long Call', type: 'bullish', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 0 }
  ]},
  { name: 'Short Put', type: 'bullish', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: 0 }
  ]},
  { name: 'Bull Call Spread', type: 'bullish', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 }
  ]},
  { name: 'Bull Put Spread', type: 'bullish', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -100 }
  ]},
  { name: 'Call Ratio Back Spread', type: 'bullish', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 100 }
  ]},
  { name: 'Long Synthetic', type: 'bullish', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: 0 }
  ]},
  { name: 'Range Forward', type: 'bullish', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 }
  ]},
  { name: 'Bullish Butterfly', type: 'bullish', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 200 }
  ]},
  { name: 'Bullish Condor', type: 'bullish', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 200 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 300 }
  ]},

  // ===== BEARISH =====
  { name: 'Short Call', type: 'bearish', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 0 }
  ]},
  { name: 'Long Put', type: 'bearish', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: 0 }
  ]},
  { name: 'Bear Call Spread', type: 'bearish', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 100 }
  ]},
  { name: 'Bear Put Spread', type: 'bearish', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 }
  ]},
  { name: 'Put Ratio Back Spread', type: 'bearish', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -100 }
  ]},
  { name: 'Short Synthetic', type: 'bearish', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 0 }
  ]},
  { name: 'Risk Reversal', type: 'bearish', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 }
  ]},
  { name: 'Bearish Butterfly', type: 'bearish', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -200 }
  ]},
  { name: 'Bearish Condor', type: 'bearish', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -200 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -300 }
  ]},

  // ===== NEUTRAL =====
  { name: 'Long Straddle', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: 0 }
  ]},
  { name: 'Short Straddle', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: 0 }
  ]},
  { name: 'Long Strangle', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -100 }
  ]},
  { name: 'Short Strangle', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 }
  ]},
  { name: 'Jade Lizard', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 200 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 }
  ]},
  { name: 'Reverse Jade Lizard', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -200 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 }
  ]},
  { name: 'Call Ratio Spread', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 }
  ]},
  { name: 'Put Ratio Spread', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 }
  ]},
  { name: 'Batman Strategy', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -300 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -200 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 200 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 300 }
  ]},
  { name: 'Long Iron Fly', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 }
  ]},
  { name: 'Short Iron Fly', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 100 }
  ]},
  { name: 'Double Fly', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -200 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 200 }
  ]},
  { name: 'Long Iron Condor', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -200 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 200 }
  ]},
  { name: 'Short Iron Condor', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -200 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 200 }
  ]},
  { name: 'Double Condor', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -300 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -200 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 200 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 300 }
  ]},
  { name: 'Call Calendar', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 0 }
  ]},
  { name: 'Put Calendar', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: 0 }
  ]},
  { name: 'Diagonal Calendar', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 0 }
  ]},
  { name: 'Call Butterfly', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: -100 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'CE', action: 'BUY', strikeOffset: 100 }
  ]},
  { name: 'Put Butterfly', type: 'neutral', legs: [
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: 100 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'PE', action: 'SELL', strikeOffset: 0 },
    { segment: 'OPTIDX', type: 'PE', action: 'BUY', strikeOffset: -100 }
  ]}
];

@Component({
  selector: 'app-strategy-builder',
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule],
  templateUrl: './strategy-builder.component.html',
  styleUrls: ['./strategy-builder.component.scss'],
  animations: [
    trigger('expandCollapse', [
      state('collapsed', style({
        height: '0',
        opacity: '0',
        overflow: 'hidden',
        paddingTop: '0',
        paddingBottom: '0'
      })),
      state('expanded', style({
        height: '*',
        opacity: '1',
        overflow: 'visible'
      })),
      transition('collapsed <=> expanded', [
        animate('300ms cubic-bezier(0.4, 0, 0.2, 1)')
      ])
    ])
  ]
})
export class StrategyBuilderComponent implements OnInit, AfterViewInit, OnDestroy {
  private destroy$ = new Subject<void>();
  private portfolioSyncTimer: ReturnType<typeof setInterval> | null = null;
  Infinity = Infinity;
  
  symbols: string[] = ['NIFTY', 'BANKNIFTY', 'FINNIFTY'];
  isLoadingSymbols = false;
  selectedSymbol: string = 'NIFTY';
  symbolDetails: any = null;
  futuresPrice: number = 0;
  currentIV: number = 0;
  pop: number = 65.5; // Estimated POP
  estMargin: number = 0;
  payoffDate: string = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
  
  expiries: string[] = [];
  strikes: number[] = [];
  chainExpiry: string = '';
  optionChainData: any[] = [];
  isChainOpen: boolean = true;
  Math = Math;

  isITM(strike: number, type: 'CE' | 'PE'): boolean {
    const spot = this.symbolDetails?.lastPrice || 0;
    if (spot === 0) return false;
    return type === 'CE' ? strike < spot : strike > spot;
  }

  getAtmStrike(): number {
    const spot = this.symbolDetails?.lastPrice || 0;
    if (spot === 0 || this.strikes.length === 0) return 0;
    return this.strikes.reduce((prev, curr) => 
      Math.abs(curr - spot) < Math.abs(prev - spot) ? curr : prev
    );
  }

  // Searchable Ticker
  searchQuery: string = 'NIFTY';
  filteredSymbols: string[] = [];
  showSymbolDropdown = false;

  filterSymbols() {
    if (!this.searchQuery) {
      this.filteredSymbols = this.symbols.slice(0, 10);
      return;
    }
    const q = this.searchQuery.toUpperCase();
    this.filteredSymbols = this.symbols
      .filter(s => s.toUpperCase().includes(q))
      .slice(0, 10);
  }

  selectSymbol(s: string) {
    this.selectedSymbol = s;
    this.searchQuery = s;
    this.showSymbolDropdown = false;
    this.onSymbolChange();
  }
  
  legs: Position[] = [];
  newLeg: Position = {
    segment: 'OPTIDX',
    expiry: '',
    strike: 0,
    option_type: 'CE',
    action: 'BUY',
    qty: 1,
    entry_price: 0
  };

  view: 'bullish' | 'bearish' | 'neutral' = 'bullish';
  activeTab: 'builder' | 'saved' = 'builder';
  
  // Preset modal state
  showPresetModal = false;
  activePreset: any = null;
  presetLegs: any[] = [];
  presetExpiry: string = '';
  presetLotQty: number = 1;
  
  userStrategies: UserStrategies = { live: [], history: [] };
  
  chart: any;
  summary = {
    pop: 0,
    maxProfit: 0 as number | string,
    maxLoss: 0 as number | string,
    rrRatio: 'N/A',
    breakeven: [] as number[],
    netCredit: 0,
    margin: 0
  };
  
  showSaveModal = false;
  strategyName = '';
  isLoading = false;
  portfolioPositions: PortfolioSyncedHolding[] = [];
  portfolioPositionsLoading = false;
  portfolioPositionsError = '';
  portfolioPositionsUpdatedAt: Date | null = null;

  constructor(private strategyService: StrategyService) {}

  ngOnInit() {
    this.loadSymbols();
    this.loadPortfolioPositions();
    this.startPortfolioSync();
  }

  ngAfterViewInit() {
    this.initChart();
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
    if (this.portfolioSyncTimer) {
      clearInterval(this.portfolioSyncTimer);
      this.portfolioSyncTimer = null;
    }
  }

  get optionPortfolioPositions(): PortfolioSyncedHolding[] {
    return this.portfolioPositions.filter((p) => p.instrument_type === 'OPTION');
  }

  get matchingOptionPositions(): PortfolioSyncedHolding[] {
    const symbol = this.selectedSymbol.toUpperCase();
    return this.optionPortfolioPositions.filter((p) => p.symbol.toUpperCase() === symbol);
  }

  private startPortfolioSync() {
    this.portfolioSyncTimer = setInterval(() => {
      this.loadPortfolioPositions(true);
    }, 30000);
  }

  loadPortfolioPositions(silent = false) {
    if (!silent) {
      this.portfolioPositionsLoading = true;
    }
    this.portfolioPositionsError = '';

    this.strategyService.getPortfolioHoldings().subscribe({
      next: (res) => {
        this.portfolioPositions = Array.isArray(res?.holdings) ? res.holdings : [];
        this.portfolioPositionsUpdatedAt = new Date();
        this.portfolioPositionsLoading = false;
      },
      error: () => {
        this.portfolioPositionsLoading = false;
        if (!silent) {
          this.portfolioPositionsError = 'Unable to load synced portfolio positions right now.';
        }
      }
    });
  }

  addPortfolioOptionToBuilder(position: PortfolioSyncedHolding) {
    if (!position.expiry || !position.strike || !position.option_type || !position.action) {
      return;
    }

    const positionSymbol = position.symbol.toUpperCase();
    if (positionSymbol && positionSymbol !== this.selectedSymbol.toUpperCase()) {
      this.selectedSymbol = positionSymbol;
      this.searchQuery = positionSymbol;
      this.onSymbolChange();
    }

    this.chainExpiry = position.expiry;
    this.newLeg.expiry = position.expiry;

    const lotSize = Math.max(1, Number(position.lot_size || this.symbolDetails?.lotSize || 1));
    const lots = Math.max(1, Number(position.lots || Math.round(position.qty / lotSize) || 1));
    const indexSymbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY'];
    const segment = indexSymbols.includes(position.symbol.toUpperCase()) ? 'OPTIDX' : 'OPTSTK';

    this.legs.push({
      segment,
      expiry: position.expiry,
      strike: Number(position.strike),
      option_type: position.option_type,
      action: position.action,
      qty: lots,
      entry_price: Number(position.avg_price || 0),
      symbol: position.symbol,
    });

    setTimeout(() => {
      this.initChart();
      this.updateChart();
    }, 100);
  }

  loadSymbols() {
    this.isLoadingSymbols = true;
    this.strategyService.getSymbols().subscribe({
      next: (res) => {
        if (res.symbols && res.symbols.length > 0) {
          this.symbols = res.symbols;
        }
        this.isLoadingSymbols = false;
        this.onSymbolChange();
      },
      error: () => {
        this.isLoadingSymbols = false;
        this.onSymbolChange(); // At least load NIFTY defaults
      }
    });
    this.loadUserStrategies();
  }

  loadUserStrategies() {
    this.strategyService.getUserStrategies().subscribe(res => {
      this.userStrategies = res;
    });
  }

  onSymbolChange() {
    this.searchQuery = this.selectedSymbol;
    this.filterSymbols();
    this.isLoading = true;
    const isIndex = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY'].includes(this.selectedSymbol.toUpperCase());
    
    this.strategyService.getDropdowns(this.selectedSymbol).subscribe({
      next: (res: any) => {
        this.expiries = res.expiryDates || res.expiryDate || [];
        const lotSize = res.lotSize || 1;
        
        if (!this.symbolDetails) {
          this.symbolDetails = { lastPrice: 0, lotSize: lotSize };
        } else {
          this.symbolDetails.lotSize = lotSize;
        }

        if (this.expiries.length > 0) {
          this.chainExpiry = this.expiries[0];
          this.newLeg.expiry = this.chainExpiry;
          this.loadOptionChain();
          this.fetchFuturesPrice();
        }
        this.isLoading = false;
        this.updateChart();
      },
      error: () => {
        this.isLoading = false;
        this.updateChart();
      }
    });

    this.strategyService.getSymbolData(this.selectedSymbol).subscribe({
      next: (res: any) => {
        let lastPrice = 0;
        if (isIndex) {
          lastPrice = res?.last || res?.lastPrice || 0;
        } else {
          lastPrice = res?.tradeInfo?.lastPrice || 
                      res?.priceInfo?.lastPrice || 
                      res?.metadata?.lastPrice ||
                      res?.equityResponse?.[0]?.orderBook?.lastPrice || 0;
        }

        if (!this.symbolDetails) {
          this.symbolDetails = { lastPrice: lastPrice, lotSize: 1 };
        } else {
          this.symbolDetails.lastPrice = lastPrice;
        }
        this.currentIV = res?.iv || 20;
        this.updateChart();
      }
    });
  }

  fetchFuturesPrice() {
    if (!this.selectedSymbol || !this.chainExpiry) return;
    
    const symbol = this.selectedSymbol.toUpperCase();
    const expiry = this.chainExpiry; // e.g., 30-Mar-2026
    const isIndex = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY'].includes(symbol);
    
    if (isIndex) {
      // For indices, backend returns { nearestFuture: { lastPrice, expiryDate, ... }, futuresData: [...] }
      this.strategyService.getFuturesData(symbol, '', '').subscribe({
        next: (res: any) => {
          this.futuresPrice = res.nearestFuture?.lastPrice || 
                              this.symbolDetails?.lastPrice || 0;
        }
      });
    } else {
      // Stock futures: build identifier
      const months: any = { 'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06', 
                            'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12' };
      
      const parts = expiry.split('-');
      if (parts.length < 3) return;
      const numericExpiry = `${parts[0]}-${months[parts[1]] || '01'}-${parts[2]}`;
      const identifier = `FUTSTK${symbol}${numericExpiry}XX0.00`;
      
      this.strategyService.getFuturesData(symbol, expiry, identifier).subscribe({
        next: (res: any) => {
          this.futuresPrice = res.data?.[0]?.lastPrice || res.lastPrice || 
                              res.tradeInfo?.lastPrice || res.priceInfo?.lastPrice || 0;
        }
      });
    }
  }

  loadOptionChain() {
    if (!this.selectedSymbol) return;
    this.strategyService.getOptionChain(this.selectedSymbol, this.chainExpiry).subscribe({
      next: (res: any) => {
        const rawData = res.filtered?.data || res.data || [];
        this.optionChainData = rawData; // Keep this for other uses of optionChainData
        this.strikes = rawData.map((d: any) => d.strikePrice).sort((a: number, b: number) => a - b);
        
        const lastPrice = res.underlyingValue || res.records?.underlyingValue || this.symbolDetails?.lastPrice || 0;
        let atm: any = null;
        const dte = this.getDTE() / 365;
        const r = 0.07;

        if (lastPrice > 0 && rawData.length > 0) {
          atm = rawData.reduce((prev: any, curr: any) => {
            return (Math.abs(curr.strikePrice - lastPrice) < Math.abs(prev.strikePrice - lastPrice) ? curr : prev);
          });
          this.currentIV = atm?.CE?.impliedVolatility || atm?.PE?.impliedVolatility || 0;
          
          // Pre-calculate Greeks with IV Solver
          this.optionChainData = rawData.map((row: any) => {
            const ceLtp = row.CE?.lastPrice || 0;
            const peLtp = row.PE?.lastPrice || 0;
            
            // Derive IV from Market Price (LTP)
            const solvedCE_IV = ceLtp > 0 ? this.solveIV(lastPrice, row.strikePrice, dte, r, ceLtp, 'CE') : 0;
            const solvedPE_IV = peLtp > 0 ? this.solveIV(lastPrice, row.strikePrice, dte, r, peLtp, 'PE') : 0;

            // Calculate Greeks with either solved IV or ATM fallback
            const calcCE_IV = solvedCE_IV > 0 ? solvedCE_IV : (this.currentIV || 20);
            const calcPE_IV = solvedPE_IV > 0 ? solvedPE_IV : (this.currentIV || 20);

            const ceBS = this.calculateBS(lastPrice, row.strikePrice, dte, r, calcCE_IV / 100, 'CE');
            const peBS = this.calculateBS(lastPrice, row.strikePrice, dte, r, calcPE_IV / 100, 'PE');

            return {
              ...row,
              CE: row.CE ? { 
                ...row.CE, 
                impliedVolatility: solvedCE_IV, 
                delta: ceBS.delta,
                probITM: ceLtp > 0 ? ceBS.probITM : null 
              } : null,
              PE: row.PE ? { 
                ...row.PE, 
                impliedVolatility: solvedPE_IV, 
                delta: peBS.delta,
                probITM: peLtp > 0 ? peBS.probITM : null
              } : null
            };
          });
        }
        
        // Update newLeg price for the selected expiry/strike
        if (!this.newLeg.strike) {
            this.newLeg.strike = atm?.strikePrice || this.strikes[Math.floor(this.strikes.length / 2)];
        }
        this.updateNewLegPrice();
        this.updateChart();
      }
    });
  }

  onManualExpiryChange() {
    this.chainExpiry = this.newLeg.expiry; // Sync chain with manual select
    this.fetchFuturesPrice();
    this.loadOptionChain();
  }

  onManualStrikeChange() {
    this.updateNewLegPrice();
  }

  onManualTypeChange() {
    this.updateNewLegPrice();
  }

  updateNewLegPrice() {
    // Use already-loaded option chain data (no extra API call)
    // Number() coercion needed because <select> returns strings
    const strike = Number(this.newLeg.strike);
    const row = this.optionChainData.find((d: any) => d.strikePrice === strike);
    if (row) {
      const price = this.newLeg.option_type === 'CE' ? row.CE?.lastPrice : row.PE?.lastPrice;
      this.newLeg.entry_price = price || 0;
    } else {
      // Fallback: fetch from API if chain not loaded yet
      this.strategyService.getOptionChain(this.selectedSymbol, this.newLeg.expiry).subscribe(res => {
        const data = res.data || [];
        const apiRow = data.find((d: any) => d.strikePrice === strike);
        if (apiRow) {
          this.newLeg.entry_price = this.newLeg.option_type === 'CE' ? apiRow.CE?.lastPrice : apiRow.PE?.lastPrice;
        }
      });
    }
  }

  reset() {
    this.legs = [];
    this.updateChart();
  }

  addFromChain(row: any, type: 'CE' | 'PE') {
    const ltp = type === 'CE' ? row.CE?.lastPrice : row.PE?.lastPrice;
    if (!ltp) return;

    this.legs.push({
      segment: 'OPTIDX',
      expiry: this.chainExpiry,
      strike: row.strikePrice,
      option_type: type,
      action: 'BUY',
      qty: 1,
      entry_price: ltp
    });
    setTimeout(() => {
      this.initChart();
      this.updateChart();
    }, 100);
    // Scroll to active legs
    document.querySelector('.legs-panel')?.scrollIntoView({ behavior: 'smooth' });
  }

  addManualLeg() {
    this.legs.push({ ...this.newLeg });
    setTimeout(() => {
      this.initChart();
      this.updateChart();
    }, 100);
    document.querySelector('.legs-panel')?.scrollIntoView({ behavior: 'smooth' });
  }

  removeLeg(index: number) {
    this.legs.splice(index, 1);
    this.updateChart();
  }

  setView(view: 'bullish' | 'bearish' | 'neutral') {
    this.view = view;
  }

  getFilteredStrategies() {
    return STRATEGY_PRESETS.filter(ts => ts.type === this.view);
  }

  applyPreset(preset: any) {
    this.openPresetModal(preset);
  }

  openPresetModal(preset: any) {
    if (!this.symbolDetails) return;
    this.activePreset = preset;
    this.presetExpiry = this.chainExpiry || this.expiries[0] || '';
    this.presetLotQty = 1;
    const spot = this.symbolDetails.lastPrice || 0;
    
    this.presetLegs = preset.legs.map((l: any) => {
      const strike = Math.round((spot + l.strikeOffset) / 100) * 100;
      const row = this.optionChainData.find((d: any) => d.strikePrice === strike);
      const ltp = row ? (l.type === 'CE' ? row.CE?.lastPrice : row.PE?.lastPrice) : 0;
      const iv = row ? (l.type === 'CE' ? row.CE?.impliedVolatility : row.PE?.impliedVolatility) : 0;
      
      return {
        type: l.type,
        action: l.action,
        strike: strike,
        ltp: ltp || 0,
        iv: iv || 0,
        mult: l.action === 'BUY' ? '+1' : '-1'
      };
    });
    this.showPresetModal = true;
  }

  onPresetStrikeChange(legIndex: number) {
    const leg = this.presetLegs[legIndex];
    const strike = Number(leg.strike);
    const row = this.optionChainData.find((d: any) => d.strikePrice === strike);
    if (row) {
      leg.ltp = (leg.type === 'CE' ? row.CE?.lastPrice : row.PE?.lastPrice) || 0;
      leg.iv = (leg.type === 'CE' ? row.CE?.impliedVolatility : row.PE?.impliedVolatility) || 0;
    } else {
      leg.ltp = 0;
      leg.iv = 0;
    }
  }

  onPresetExpiryChange() {
    if (!this.activePreset || !this.presetExpiry) return;
    this.isLoading = true;
    
    this.strategyService.getOptionChain(this.selectedSymbol, this.presetExpiry).subscribe({
      next: (res: any) => {
        const rawData = res.filtered?.data || res.data || [];
        const spot = res.underlyingValue || res.records?.underlyingValue || this.symbolDetails?.lastPrice || 0;
        
        // Update each leg's price based on the new expiry's chain
        this.presetLegs.forEach(leg => {
          const row = rawData.find((d: any) => d.strikePrice === Number(leg.strike));
          if (row) {
            leg.ltp = (leg.type === 'CE' ? row.CE?.lastPrice : row.PE?.lastPrice) || 0;
            leg.iv = (leg.type === 'CE' ? row.CE?.impliedVolatility : row.PE?.impliedVolatility) || 0;
          } else {
            leg.ltp = 0;
            leg.iv = 0;
          }
        });
        
        this.isLoading = false;
      },
      error: () => this.isLoading = false
    });
  }

  confirmPreset() {
    if (!this.activePreset) return;
    const lotSize = this.symbolDetails?.lotSize || 1;
    
    this.legs = this.presetLegs.map(l => ({
      segment: 'OPTIDX',
      expiry: this.presetExpiry,
      strike: Number(l.strike),
      option_type: l.type,
      action: l.action,
      qty: this.presetLotQty,
      entry_price: l.ltp || 0
    }));
    
    this.showPresetModal = false;
    this.activePreset = null;
    setTimeout(() => {
      this.initChart();
      this.updateChart();
    }, 100);
  }

  closePresetModal() {
    this.showPresetModal = false;
    this.activePreset = null;
  }


  getThumbnailPath(name: string): string {
    const paths: any = {
      // Bullish
      'Long Call':              'M 10 40 L 50 40 L 90 10',
      'Short Put':              'M 10 10 L 50 40 L 90 40',
      'Bull Call Spread':       'M 10 40 L 35 40 L 55 15 L 90 15',
      'Bull Put Spread':        'M 10 15 L 45 15 L 65 40 L 90 40',
      'Call Ratio Back Spread': 'M 10 30 L 35 40 L 55 40 L 90 5',
      'Long Synthetic':         'M 10 45 L 50 25 L 90 5',
      'Range Forward':          'M 10 40 L 30 40 L 50 25 L 70 10 L 90 10',
      'Bullish Butterfly':      'M 10 35 L 30 35 L 50 10 L 65 35 L 90 35',
      'Bullish Condor':         'M 10 35 L 25 35 L 40 12 L 60 12 L 75 35 L 90 35',
      // Bearish
      'Short Call':             'M 10 40 L 50 40 L 90 10',
      'Long Put':               'M 10 10 L 50 40 L 90 40',
      'Bear Call Spread':       'M 10 15 L 45 15 L 65 40 L 90 40',
      'Bear Put Spread':        'M 10 40 L 35 40 L 55 15 L 90 15',
      'Put Ratio Back Spread':  'M 10 5 L 45 40 L 65 40 L 90 30',
      'Short Synthetic':        'M 10 5 L 50 25 L 90 45',
      'Risk Reversal':          'M 10 10 L 30 10 L 50 25 L 70 40 L 90 40',
      'Bearish Butterfly':      'M 10 35 L 30 35 L 50 10 L 65 35 L 90 35',
      'Bearish Condor':         'M 10 35 L 25 35 L 40 12 L 60 12 L 75 35 L 90 35',
      // Neutral
      'Long Straddle':          'M 10 10 L 50 40 L 90 10',
      'Short Straddle':         'M 10 40 L 50 10 L 90 40',
      'Long Strangle':          'M 10 10 L 30 40 L 70 40 L 90 10',
      'Short Strangle':         'M 10 40 L 30 10 L 70 10 L 90 40',
      'Jade Lizard':            'M 10 40 L 30 15 L 55 15 L 70 40 L 90 40',
      'Reverse Jade Lizard':    'M 10 40 L 30 40 L 45 15 L 70 15 L 90 40',
      'Call Ratio Spread':      'M 10 35 L 40 35 L 55 15 L 90 45',
      'Put Ratio Spread':       'M 10 45 L 45 15 L 60 35 L 90 35',
      'Batman Strategy':        'M 10 30 L 20 15 L 35 30 L 50 10 L 65 30 L 80 15 L 90 30',
      'Long Iron Fly':          'M 10 30 L 30 30 L 50 10 L 70 30 L 90 30',
      'Short Iron Fly':         'M 10 30 L 30 30 L 50 45 L 70 30 L 90 30',
      'Double Fly':             'M 10 30 L 20 30 L 30 10 L 40 30 L 60 30 L 70 10 L 80 30 L 90 30',
      'Long Iron Condor':       'M 10 30 L 25 30 L 35 10 L 65 10 L 75 30 L 90 30',
      'Short Iron Condor':      'M 10 30 L 25 30 L 35 45 L 65 45 L 75 30 L 90 30',
      'Double Condor':          'M 10 30 L 15 30 L 25 10 L 35 30 L 65 30 L 75 10 L 85 30 L 90 30',
      'Call Calendar':          'M 10 35 L 30 35 L 50 15 L 70 35 L 90 35',
      'Put Calendar':           'M 10 35 L 30 35 L 50 15 L 70 35 L 90 35',
      'Diagonal Calendar':      'M 10 35 L 35 35 L 55 15 L 75 35 L 90 35',
      'Call Butterfly':         'M 10 35 L 30 35 L 50 10 L 70 35 L 90 35',
      'Put Butterfly':          'M 10 35 L 30 35 L 50 10 L 70 35 L 90 35',
      'Iron Fly':               'M 10 30 L 30 30 L 50 45 L 70 30 L 90 30',
      'Iron Condor':            'M 10 30 L 25 30 L 35 45 L 65 45 L 75 30 L 90 30'
    };
    return paths[name] || 'M 10 25 L 90 25';
  }


  // Frontend Greeks Implementation (Black-Scholes)
  calculateBS(S: number, K: number, T: number, r: number, sigma: number, type: string) {
    if (T <= 0.0001) {
      const itm = type === 'CE' ? (S > K ? 1 : 0) : (S < K ? 1 : 0);
      return { 
        price: type === 'CE' ? Math.max(0, S - K) : Math.max(0, K - S), 
        delta: type === 'CE' ? itm : -itm,
        probITM: itm
      };
    }
    
    if (sigma <= 0) sigma = 0.01;
    
    const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T));
    const d2 = d1 - sigma * Math.sqrt(T);
    
    let price = 0;
    let delta = 0;
    let probITM = 0;
    
    if (type === 'CE') {
      price = S * this.cdf(d1) - K * Math.exp(-r * T) * this.cdf(d2);
      delta = this.cdf(d1);
      probITM = this.cdf(d2);
    } else {
      price = K * Math.exp(-r * T) * this.cdf(-d2) - S * this.cdf(-d1);
      delta = this.cdf(d1) - 1;
      probITM = this.cdf(-d2);
    }
    
    return { price, delta, probITM };
  }

  getLegGreeks(leg: Position) {
    const S = this.symbolDetails?.lastPrice || 0;
    const K = leg.strike || 0;
    const T = this.getDTE() / 365;
    const r = 0.07;
    const sigma = (this.currentIV || 20) / 100;
    
    if (S <= 0 || K <= 0) return { delta: 0 };

    const bs = this.calculateBS(S, K, T, r, sigma, leg.option_type || 'CE');
    const mult = leg.action === 'BUY' ? 1 : -1;
    
    return {
      delta: bs.delta * mult * (leg.qty || 1)
    };
  }

  cdf(x: number): number {
    const t = 1 / (1 + 0.2316419 * Math.abs(x));
    const d = 0.3989423 * Math.exp(-x * x / 2);
    const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.7814779 + t * (-1.821256 + t * 1.3302745))));
    return x >= 0 ? 1 - p : p;
  }

  initChart() {
    const ctx = document.getElementById('payoffChart') as HTMLCanvasElement;
    if (!ctx) return;
    if (this.chart) this.chart.destroy();

    this.chart = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [{
          label: 'Expiry Payoff',
          data: [],
          borderColor: '#10b981',
          borderWidth: 3,
          fill: true,
          backgroundColor: 'rgba(16, 185, 129, 0.05)',
          tension: 0,
          pointRadius: 0
        }, {
          label: 'Zero Line',
          data: [],
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          borderDash: [5, 5],
          pointRadius: 0,
          fill: false
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        scales: {
          x: { type: 'linear', grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b' } },
          y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b' } }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            borderColor: 'rgba(100, 116, 139, 0.3)',
            borderWidth: 1,
            titleFont: { size: 14, weight: 'bold' },
            bodyFont: { size: 13 },
            padding: 12,
            cornerRadius: 8,
            displayColors: false,
            callbacks: {
              title: (items: any) => {
                return items[0]?.parsed?.x?.toFixed(1) || '';
              },
              label: (ctx: any) => {
                const val = ctx.parsed.y;
                const spot = this.symbolDetails?.lastPrice || 0;
                const price = ctx.parsed.x;
                if (ctx.datasetIndex === 0) {
                  const pctChg = spot > 0 ? ((price - spot) / spot * 100).toFixed(2) : '0';
                  return [`P&L  ₹${val.toLocaleString('en-IN')}`, `Chg. from Spot: (${pctChg}%)`];
                }
                if (ctx.datasetIndex === 2) {
                  return `t+0 P&L  ₹${val.toLocaleString('en-IN')}`;
                }
                return ''; // hide zero line
              }
            }
          }
        }
      }
    });
  }

  updateChart() {
    if (!this.chart || !this.symbolDetails) return;

    const spot = this.symbolDetails.lastPrice || 100;
    const lotSize = this.symbolDetails.lotSize || 1;
    const range = spot * 0.20; // +/- 20% (like Opstra)
    const steps = 200; // Fine resolution for precise breakeven
    const stepSize = (range * 2) / steps;
    const sigma = (this.currentIV || 20) / 100; // Actual market IV
    const chartDte = this.getEffectiveDTE() / 365;
    const r = 0.07;
    
    const payoffData: {x: number, y: number}[] = [];
    const t0Data: {x: number, y: number}[] = [];
    const zeroLine: {x: number, y: number}[] = [];

    for (let i = 0; i <= steps; i++) {
      const curS = (spot - range) + (i * stepSize);
      let totalP = 0;
      let totalT0 = 0;

      for (const leg of this.legs) {
        const mult = leg.action === 'BUY' ? 1 : -1;
        const strike = Number(leg.strike) || 0;
        
        // Expiry Payoff
        let legP = 0;
        if (leg.option_type === 'CE') legP = (Math.max(0, curS - strike) - leg.entry_price) * mult;
        else legP = (Math.max(0, strike - curS) - leg.entry_price) * mult;
        
        // T+0 Payoff (Black-Scholes with ACTUAL IV)
        let legT0 = 0;
        const legDte = this.getLegDTE(leg.expiry) / 365;
        if (legDte > 0.0001) {
          const greeks = this.calculateBS(curS, strike, legDte, r, sigma, leg.option_type || 'CE');
          legT0 = (greeks.price - leg.entry_price) * mult;
        } else {
          legT0 = legP; // At expiry, T+0 = expiry payoff
        }

        totalP += legP * leg.qty * lotSize;
        totalT0 += legT0 * leg.qty * lotSize;
      }

      const x = parseFloat(curS.toFixed(1));
      payoffData.push({ x, y: Math.round(totalP) });
      t0Data.push({ x, y: Math.round(totalT0) });
      zeroLine.push({ x, y: 0 });
    }

    this.chart.data.datasets[0].data = payoffData;
    if (this.chart.data.datasets[2]) {
      this.chart.data.datasets[2].data = t0Data;
    } else {
      this.chart.data.datasets.push({
        label: 'T+0 Payoff',
        data: t0Data,
        borderColor: '#3b82f6',
        borderWidth: 2,
        borderDash: [5, 4],
        pointRadius: 0,
        fill: false
      });
    }
    this.chart.data.datasets[1].data = zeroLine;
    this.chart.update('none');

    // --- Summary Calculations ---

    // 1. Max Profit / Max Loss (from payoff curve)
    let maxProfit = -Infinity;
    let maxLoss = Infinity;

    for (const pt of payoffData) {
      if (pt.y > maxProfit) maxProfit = pt.y;
      if (pt.y < maxLoss) maxLoss = pt.y;
    }

    // 2. Breakevens (linear interpolation for precision)
    const bePoints: number[] = [];
    for (let i = 1; i < payoffData.length; i++) {
      const y0 = payoffData[i - 1].y;
      const y1 = payoffData[i].y;
      if ((y0 < 0 && y1 >= 0) || (y0 > 0 && y1 <= 0)) {
        // Linear interpolation: find exact x where y = 0
        const x0 = payoffData[i - 1].x;
        const x1 = payoffData[i].x;
        const be = x0 + (0 - y0) * (x1 - x0) / (y1 - y0);
        bePoints.push(parseFloat(be.toFixed(1)));
      }
    }

    // 3. Check for "Unlimited" Profit/Loss at edges
    const leftSlope = payoffData[1].y - payoffData[0].y;
    const rightSlope = payoffData[steps].y - payoffData[steps - 1].y;
    
    let displayMaxProfit: string | number = maxProfit;
    let displayMaxLoss: string | number = maxLoss;

    if (rightSlope > 1 || leftSlope < -1) displayMaxProfit = 'Unlimited';
    if (rightSlope < -1) displayMaxLoss = 'Unlimited';

    // 4. POP: Use breakeven-based N(d2) for accuracy
    let pop = 0;
    if (chartDte > 0.0001 && sigma > 0 && spot > 0 && bePoints.length > 0) {
      const sqrtT = sigma * Math.sqrt(chartDte);
      const drift = (r - 0.5 * sigma * sigma) * chartDte;

      // For a long call (profit above breakeven): POP = P(S > BE)
      // For a long put (profit below breakeven): POP = P(S < BE)
      // General: sum probability of price being in profitable zones
      
      // Determine profitable direction from the payoff curve
      const lastPayoff = payoffData[steps].y;
      const firstPayoff = payoffData[0].y;
      
      if (bePoints.length === 1) {
        const be = bePoints[0];
        const d2 = (Math.log(spot / be) + drift) / sqrtT;
        if (lastPayoff > 0) {
          // Profit on the right (like long call)
          pop = this.cdf(d2) * 100;
        } else {
          // Profit on the left (like long put)
          pop = (1 - this.cdf(d2)) * 100;
        }
      } else if (bePoints.length === 2) {
        // Profit between two breakevens (like short straddle) or outside
        const d2_low = (Math.log(spot / bePoints[0]) + drift) / sqrtT;
        const d2_high = (Math.log(spot / bePoints[1]) + drift) / sqrtT;
        
        // Check if profit is between or outside the breakevens
        const midX = (bePoints[0] + bePoints[1]) / 2;
        const midIdx = payoffData.findIndex(p => p.x >= midX);
        if (midIdx >= 0 && payoffData[midIdx].y > 0) {
          // Profit between breakevens
          pop = (this.cdf(d2_low) - this.cdf(d2_high)) * 100;
        } else {
          // Profit outside breakevens
          pop = ((1 - this.cdf(d2_low)) + this.cdf(d2_high)) * 100;
        }
      }
    }

    if (bePoints.length === 0) {
      const allPositive = payoffData.every((p) => p.y > 0);
      const allNegative = payoffData.every((p) => p.y < 0);
      if (allPositive) pop = 100;
      if (allNegative) pop = 0;
    }

    // 5. Net Premium
    let netPremium = 0;
    this.legs.forEach(l => {
      netPremium += l.entry_price * l.qty * lotSize * (l.action === 'BUY' ? -1 : 1);
    });

    this.summary = {
      pop: Math.max(0, Math.min(100, pop)),
      maxProfit: displayMaxProfit,
      maxLoss: displayMaxLoss,
      breakeven: bePoints,
      rrRatio: (typeof displayMaxProfit === 'string' || typeof displayMaxLoss === 'string') ? 'N/A' : (Math.abs(Number(displayMaxProfit) / Number(displayMaxLoss))).toFixed(2),
      netCredit: netPremium,
      margin: Math.abs(netPremium)
    };
  }

  getDTE(): number {
    if (!this.chainExpiry) return 0;
    const exp = this.parseExpiryDate(this.chainExpiry);
    if (!exp) return 0;
    const now = new Date();
    const diff = exp.getTime() - now.getTime();
    return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
  }

  private getLegDTE(expiry?: string): number {
    if (!expiry) return this.getDTE();
    const parsed = this.parseExpiryDate(expiry);
    if (!parsed) return this.getDTE();
    const now = new Date();
    const diff = parsed.getTime() - now.getTime();
    return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
  }

  private getEffectiveDTE(): number {
    const legDtes = this.legs
      .map((l) => this.getLegDTE(l.expiry))
      .filter((v) => Number.isFinite(v) && v >= 0);
    if (legDtes.length === 0) {
      return this.getDTE();
    }
    return Math.min(...legDtes);
  }

  private parseExpiryDate(value: string): Date | null {
    const raw = String(value || '').trim();
    if (!raw) return null;

    const direct = new Date(raw);
    if (!Number.isNaN(direct.getTime())) {
      return direct;
    }

    const match = raw.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/);
    if (!match) return null;

    const months: Record<string, number> = {
      JAN: 0, FEB: 1, MAR: 2, APR: 3, MAY: 4, JUN: 5,
      JUL: 6, AUG: 7, SEP: 8, OCT: 9, NOV: 10, DEC: 11,
    };

    const day = Number(match[1]);
    const mon = months[match[2].toUpperCase()];
    const year = Number(match[3]);
    if (!Number.isFinite(day) || mon === undefined || !Number.isFinite(year)) {
      return null;
    }

    return new Date(year, mon, day);
  }

  getPayoffDTE(): number {
    if (!this.expiries[0]) return 0;
    const exp = new Date(this.expiries[0]);
    const target = new Date(this.payoffDate);
    const diff = exp.getTime() - target.getTime();
    return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
  }

  solveIV(S: number, K: number, T: number, r: number, marketPrice: number, type: string): number {
    if (marketPrice <= 0) return 20;
    let low = 0.01;
    let high = 5.0; // 500% max
    let iv = 0.20;
    
    // Bisection for stability
    for (let i = 0; i < 20; i++) {
        iv = (low + high) / 2;
        const price = this.calculateBS(S, K, T, r, iv, type).price;
        if (price > marketPrice) high = iv;
        else low = iv;
    }
    return iv * 100;
  }

  openSaveModal() { this.showSaveModal = true; }

  save() {
    if (!this.strategyName) return;
    const strategy: Strategy = { name: this.strategyName, symbol: this.selectedSymbol, positions: this.legs };
    this.strategyService.saveStrategy(strategy).subscribe(() => {
      this.showSaveModal = false;
      this.strategyName = '';
      this.loadUserStrategies();
      alert('Strategy Saved Successfully!');
    });
  }
}
