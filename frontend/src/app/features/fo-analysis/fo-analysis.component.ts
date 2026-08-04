import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  FOService,
  NiftyData,
  OptionChainData,
  OptionChainRow,
  FuturesTableData,
} from '../../core/services/fo.service';
import { LucideAngularModule } from 'lucide-angular';
import { SearchableSelectComponent } from '../../shared/components/searchable-select/searchable-select.component';

type Tab = 'momentum' | 'nifty' | 'futures' | 'options';

@Component({
  selector: 'app-fo-analysis',
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule, SearchableSelectComponent],
  templateUrl: './fo-analysis.component.html',
  styleUrl: './fo-analysis.component.scss'
})
export class FOAnalysisComponent implements OnInit {
  activeTab: Tab = 'momentum';
  selectedDate = '';

  loading = false;
  error: string | null = null;

  math = Math;

  // --- Momentum screener ---
  momentumData: any = null;
  momentumExpiry = '';

  // --- NIFTY index tab ---
  niftyData: NiftyData | null = null;
  niftySymbol = 'NIFTY';
  niftyExpiry = '';

  // --- Futures tab ---
  futuresTable: FuturesTableData | null = null;
  futuresSegment: 'index' | 'stock' = 'index';
  futuresExpiry = '';
  futuresSymbol = '';

  // --- Options tab ---
  optionsData: OptionChainData | null = null;
  optionsSymbol = 'NIFTY';
  optionsExpiry = '';

  /** Largest CE/PE open interest in the visible chain - drives the OI bar widths. */
  private maxChainOi = 1;

  constructor(private foService: FOService) { }

  ngOnInit(): void {
    this.loadMomentumData();
  }

  // ---------------------------------------------------------------- loaders

  loadMomentumData(): void {
    this.startLoad();
    this.foService.getFuturesAnalysis(this.selectedDate, this.momentumExpiry).subscribe({
      next: (data) => {
        this.momentumData = data;
        if (!this.momentumExpiry) this.momentumExpiry = data.expiry_date || '';
        this.loading = false;
      },
      error: (err) => this.failLoad(err, 'Failed to load momentum data')
    });
  }

  loadNiftyData(): void {
    this.startLoad();
    this.foService.getNiftyData(this.selectedDate, this.niftySymbol, this.niftyExpiry).subscribe({
      next: (data) => {
        this.niftyData = data;
        this.niftySymbol = data.symbol;
        this.niftyExpiry = data.expiry || '';
        this.computeMaxChainOi(data.chain);
        this.loading = false;
      },
      error: (err) => {
        this.niftyData = null;
        this.failLoad(err, 'Failed to load NIFTY data');
      }
    });
  }

  loadFuturesData(): void {
    this.startLoad();
    this.foService.getFuturesTable(
      this.futuresSegment, this.selectedDate, this.futuresExpiry, this.futuresSymbol
    ).subscribe({
      next: (data) => {
        this.futuresTable = data;
        this.futuresExpiry = data.expiry || '';
        this.futuresSymbol = data.symbol || '';
        this.loading = false;
      },
      error: (err) => {
        this.futuresTable = null;
        this.failLoad(err, 'Failed to load futures data');
      }
    });
  }

  loadOptionsData(): void {
    this.startLoad();
    this.foService.getOptionsData(this.optionsSymbol, this.selectedDate, this.optionsExpiry).subscribe({
      next: (data) => {
        this.optionsData = data;
        this.optionsExpiry = data.expiry || '';
        this.computeMaxChainOi(data.chain);
        this.loading = false;
      },
      error: (err) => {
        this.optionsData = null;
        this.failLoad(err, 'Failed to load options data');
      }
    });
  }

  private startLoad(): void {
    this.loading = true;
    this.error = null;
  }

  private failLoad(err: any, fallback: string): void {
    this.error = err?.error?.detail || fallback;
    this.loading = false;
  }

  // ------------------------------------------------------------ chain view

  /** The chain currently on screen - the NIFTY and Options tabs share the table. */
  get activeChain(): OptionChainData | null {
    return this.activeTab === 'nifty' ? this.niftyData : this.optionsData;
  }

  private computeMaxChainOi(chain: OptionChainRow[]): void {
    const values = (chain || []).flatMap(r => [r.CE_OpnIntrst || 0, r.PE_OpnIntrst || 0]);
    this.maxChainOi = Math.max(1, ...values);
  }

  /** Width % for the open-interest bar behind a chain cell. */
  oiBarWidth(value: number | null): number {
    if (!value || value <= 0) return 0;
    return Math.min(100, (value / this.maxChainOi) * 100);
  }

  /** In-the-money strikes are shaded, as on the NSE chain. */
  isCallItm(row: OptionChainRow): boolean {
    const spot = this.activeChain?.underlying_price;
    return spot != null && row.StrkPric < spot;
  }

  isPutItm(row: OptionChainRow): boolean {
    const spot = this.activeChain?.underlying_price;
    return spot != null && row.StrkPric > spot;
  }

  isAtm(row: OptionChainRow): boolean {
    return this.activeChain?.summary?.atm_strike === row.StrkPric;
  }

  // ------------------------------------------------------------- handlers

  onTabChange(tab: Tab): void {
    this.activeTab = tab;
    this.error = null;

    switch (tab) {
      case 'momentum':
        if (!this.momentumData) this.loadMomentumData();
        break;
      case 'nifty':
        if (!this.niftyData) this.loadNiftyData();
        else this.computeMaxChainOi(this.niftyData.chain);
        break;
      case 'futures':
        if (!this.futuresTable) this.loadFuturesData();
        break;
      case 'options':
        if (!this.optionsData) this.loadOptionsData();
        else this.computeMaxChainOi(this.optionsData.chain);
        break;
    }
  }

  onNiftySymbolChange(): void {
    this.niftyExpiry = ''; // expiries differ per index - let the backend pick the nearest
    this.loadNiftyData();
  }

  onOptionsSymbolChange(symbol: string): void {
    this.optionsSymbol = symbol;
    this.optionsExpiry = '';
    this.loadOptionsData();
  }

  onFuturesSymbolChange(symbol: string): void {
    this.futuresSymbol = symbol;
    this.loadFuturesData();
  }

  onFuturesSegmentChange(segment: 'index' | 'stock'): void {
    if (this.futuresSegment === segment) return;
    this.futuresSegment = segment;
    this.futuresExpiry = '';
    this.futuresSymbol = '';
    this.loadFuturesData();
  }

  refresh(): void {
    switch (this.activeTab) {
      case 'momentum': this.loadMomentumData(); break;
      case 'nifty': this.loadNiftyData(); break;
      case 'futures': this.loadFuturesData(); break;
      case 'options': this.loadOptionsData(); break;
    }
  }

  /** Latest data date shown in the filter strip, whichever tab is open. */
  get dataDate(): string | null {
    return this.momentumData?.date || this.niftyData?.date
      || this.futuresTable?.date || this.optionsData?.date || null;
  }
}
