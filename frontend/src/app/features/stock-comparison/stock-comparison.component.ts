import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { StockService, StockComparison, ComparisonItem, SymbolSearchResult } from '../../core/services/stock.service';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged } from 'rxjs/operators';

@Component({
  selector: 'app-stock-comparison',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './stock-comparison.component.html',
  styleUrl: './stock-comparison.component.scss'
})
export class StockComparisonComponent implements OnInit {
  date1 = '';
  date2 = '';
  symbols = '';

  loading = false;
  error: string | null = null;
  comparison: StockComparison | null = null;

  availableSymbols: string[] = [];
  activeTab: 'gainers' | 'losers' | 'all' = 'all';

  // Autocomplete suggestions
  suggestions: SymbolSearchResult[] = [];
  showSuggestions = false;

  // Table filter search
  tableSearchQuery = '';

  // Debounce subject for autocomplete
  private searchSubject = new Subject<string>();

  constructor(private stockService: StockService) { }

  ngOnInit(): void {
    // Set default dates (today and yesterday)
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    this.date2 = this.formatDate(today);
    this.date1 = this.formatDate(yesterday);

    // Load available symbols
    this.loadSymbols();

    // Setup debounced search for autocomplete
    this.searchSubject.pipe(
      debounceTime(300),
      distinctUntilChanged()
    ).subscribe(query => {
      if (query.length >= 1) {
        this.fetchSuggestions(query);
      } else {
        this.suggestions = [];
      }
    });
  }

  private formatDate(date: Date): string {
    return date.toISOString().split('T')[0];
  }

  loadSymbols(): void {
    this.stockService.getSymbols().subscribe({
      next: (response) => {
        this.availableSymbols = response.symbols;
      },
      error: (err) => {
        console.error('Failed to load symbols', err);
      }
    });
  }

  onSymbolInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    const value = input.value;
    // Get the last symbol being typed (after the last comma)
    const parts = value.split(',');
    const lastPart = parts[parts.length - 1].trim();
    this.searchSubject.next(lastPart);
  }

  private fetchSuggestions(query: string): void {
    this.stockService.searchSymbols(query, 10).subscribe({
      next: (response) => {
        this.suggestions = response.results;
        this.showSuggestions = this.suggestions.length > 0;
      },
      error: () => {
        this.suggestions = [];
        this.showSuggestions = false;
      }
    });
  }

  selectSuggestion(suggestion: SymbolSearchResult): void {
    // Add the selected symbol to the input (append if there are existing symbols)
    const parts = this.symbols.split(',').map(s => s.trim()).filter(s => s);
    // Replace the last part (which user was typing) with the selected symbol
    if (parts.length > 0) {
      parts[parts.length - 1] = suggestion.symbol;
    } else {
      parts.push(suggestion.symbol);
    }
    this.symbols = parts.join(', ');
    this.showSuggestions = false;
    this.suggestions = [];
  }

  hideSuggestions(): void {
    // Delay hiding to allow click on suggestion
    setTimeout(() => {
      this.showSuggestions = false;
    }, 200);
  }

  compareStocks(): void {
    if (!this.date1 || !this.date2) {
      this.error = 'Please select both dates';
      return;
    }

    this.loading = true;
    this.error = null;
    this.comparison = null;

    this.stockService.compareStocks(this.date1, this.date2, this.symbols).subscribe({
      next: (data) => {
        this.comparison = data;
        this.loading = false;
      },
      error: (err) => {
        this.error = err.error?.detail || 'Failed to fetch comparison data';
        this.loading = false;
      }
    });
  }

  get displayedData(): ComparisonItem[] {
    if (!this.comparison) return [];

    switch (this.activeTab) {
      case 'gainers':
        return this.comparison.gainers;
      case 'losers':
        return this.comparison.losers;
      default:
        return this.filterByTableSearch(this.comparison.data);
    }
  }

  private filterByTableSearch(data: ComparisonItem[]): ComparisonItem[] {
    if (!this.tableSearchQuery.trim()) {
      return data;
    }
    const query = this.tableSearchQuery.trim().toUpperCase();
    return data.filter(item => item.Symbol.toUpperCase().includes(query));
  }

  getChangeClass(change: number): string {
    if (change > 0) return 'positive';
    if (change < 0) return 'negative';
    return '';
  }
}
