import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { FOService, NiftyData } from '../../core/services/fo.service';

@Component({
  selector: 'app-fo-analysis',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './fo-analysis.component.html',
  styleUrl: './fo-analysis.component.scss'
})
export class FOAnalysisComponent implements OnInit {
  activeTab: 'futures' | 'options' | 'nifty' = 'nifty';
  selectedDate = '';
  symbol = 'NIFTY';
  optionType = '';

  loading = false;
  error: string | null = null;

  niftyData: NiftyData | null = null;
  futuresData: any[] = [];
  optionsData: any[] = [];

  // Filtering Properties for NIFTY Tab
  uniqueSymbols: string[] = [];
  uniqueExpiries: string[] = [];
  selectedSymbol: string = 'NIFTY'; // Default
  selectedExpiry: string = '';

  filteredFutures: any[] = [];
  filteredOptions: any[] = [];

  constructor(private foService: FOService) { }

  ngOnInit(): void {
    this.selectedDate = this.formatDate(new Date());
    this.loadNiftyData();
  }

  private formatDate(date: Date): string {
    return date.toISOString().split('T')[0];
  }

  loadNiftyData(): void {
    this.loading = true;
    this.error = null;

    this.foService.getNiftyData(this.selectedDate).subscribe({
      next: (data) => {
        this.niftyData = data;
        this.processNiftyDataForFiltering(data);
        this.loading = false;
      },
      error: (err) => {
        this.error = err.error?.detail || 'Failed to load NIFTY data';
        this.loading = false;
        // Reset filters on error
        this.resetFilters();
      }
    });
  }

  loadFuturesData(): void {
    this.loading = true;
    this.error = null;

    this.foService.getFuturesData(this.symbol, this.selectedDate).subscribe({
      next: (data) => {
        this.futuresData = data.data;
        this.loading = false;
      },
      error: (err) => {
        this.error = err.error?.detail || 'Failed to load futures data';
        this.loading = false;
      }
    });
  }

  loadOptionsData(): void {
    this.loading = true;
    this.error = null;

    this.foService.getOptionsData(this.symbol, this.selectedDate, this.optionType).subscribe({
      next: (data) => {
        this.optionsData = data.data;
        this.loading = false;
      },
      error: (err) => {
        this.error = err.error?.detail || 'Failed to load options data';
        this.loading = false;
      }
    });
  }

  private processNiftyDataForFiltering(data: NiftyData): void {
    // Combine futures and options to find all unique symbols and expiries
    const allItems = [...(data.futures || []), ...(data.options || [])];

    if (allItems.length === 0) {
      this.resetFilters();
      return;
    }

    // Extract Unique Symbols
    this.uniqueSymbols = [...new Set(allItems.map(item => item.TckrSymb || item.UndrlygVal || ''))].filter(Boolean).sort();

    // Set default symbol if current selection is invalid
    if (!this.selectedSymbol || !this.uniqueSymbols.includes(this.selectedSymbol)) {
      // Prefer 'NIFTY' or 'BANKNIFTY' if available, else first one
      if (this.uniqueSymbols.includes('NIFTY')) this.selectedSymbol = 'NIFTY';
      else if (this.uniqueSymbols.includes('BANKNIFTY')) this.selectedSymbol = 'BANKNIFTY';
      else this.selectedSymbol = this.uniqueSymbols[0] || '';
    }

    // Extract Unique Expiries for the selected symbol specifically (or all if that's preferred, but usually dependent on symbol)
    // Actually expiries are global for the day mostly, but let's filter by symbol first for correctness?
    // The Streamlit logic filters expiries AFTER symbol selection.
    this.updateExpiriesForSymbol();

    this.applyFilters();
  }

  updateExpiriesForSymbol(): void {
    if (!this.niftyData) return;

    const allItems = [...(this.niftyData.futures || []), ...(this.niftyData.options || [])];
    const symbolItems = allItems.filter(item =>
      (item.TckrSymb === this.selectedSymbol) || (item.UndrlygVal === this.selectedSymbol)
    );

    // Extract Expiries
    const unsortedExpiries = [...new Set(symbolItems.map(item => item.XpryDt))].filter(Boolean);

    // Sort dates
    this.uniqueExpiries = unsortedExpiries.sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

    // Select nearest expiry by default if none selected or invalid
    if (!this.selectedExpiry || !this.uniqueExpiries.includes(this.selectedExpiry)) {
      this.selectedExpiry = this.uniqueExpiries[0] || '';
    }
  }

  onSymbolChange(): void {
    this.updateExpiriesForSymbol();
    this.applyFilters();
  }

  onExpiryChange(): void {
    this.applyFilters();
  }

  applyFilters(): void {
    if (!this.niftyData) return;

    // Filter Futures
    this.filteredFutures = (this.niftyData.futures || []).filter(item => {
      const matchSymbol = (item.TckrSymb === this.selectedSymbol) || (item.UndrlygVal === this.selectedSymbol);
      const matchExpiry = item.XpryDt === this.selectedExpiry;
      return matchSymbol && matchExpiry;
    });

    // Filter Options
    this.filteredOptions = (this.niftyData.options || []).filter(item => {
      const matchSymbol = (item.TckrSymb === this.selectedSymbol) || (item.UndrlygVal === this.selectedSymbol);
      const matchExpiry = item.XpryDt === this.selectedExpiry;
      return matchSymbol && matchExpiry;
    });
  }

  resetFilters(): void {
    this.uniqueSymbols = [];
    this.uniqueExpiries = [];
    this.filteredFutures = [];
    this.filteredOptions = [];
  }

  onTabChange(tab: 'futures' | 'options' | 'nifty'): void {
    this.activeTab = tab;
    this.error = null;

    switch (tab) {
      case 'nifty':
        if (!this.niftyData) this.loadNiftyData();
        break;
      case 'futures':
        this.loadFuturesData();
        break;
      case 'options':
        this.loadOptionsData();
        break;
    }
  }

  refresh(): void {
    switch (this.activeTab) {
      case 'nifty':
        this.loadNiftyData();
        break;
      case 'futures':
        this.loadFuturesData();
        break;
      case 'options':
        this.loadOptionsData();
        break;
    }
  }
}
