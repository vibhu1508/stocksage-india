import { Component, HostListener, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { LayoutService } from '../../../core/services/layout.service';
import { ThemeService } from '../../../core/services/theme.service';
import { ClockService } from '../../../core/services/clock.service';
import { StockService, SymbolSearchResult } from '../../../core/services/stock.service';
import { LucideAngularModule } from 'lucide-angular';
import { Observable, Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged, takeUntil } from 'rxjs/operators';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule],
  templateUrl: './header.component.html',
  styleUrl: './header.component.scss'
})
export class HeaderComponent implements OnInit, OnDestroy {
  timeParts$: Observable<any>;
  isVisible = true;
  isVideoPlaying = false;
  searchQuery = '';
  suggestions: SymbolSearchResult[] = [];
  showSuggestions = false;

  private destroy$ = new Subject<void>();
  private searchSubject = new Subject<string>();
  private lastScrollY = 0;

  constructor(
    public authService: AuthService,
    private router: Router,
    private stockService: StockService,
    private layoutService: LayoutService,
    public themeService: ThemeService,
    public clockService: ClockService
  ) { 
    this.timeParts$ = this.clockService.timeParts$;
  }

  ngOnInit() {
    this.layoutService.videoPlaying$
      .pipe(takeUntil(this.destroy$))
      .subscribe(playing => {
        this.isVideoPlaying = playing;
      });

    this.searchSubject
      .pipe(
        debounceTime(220),
        distinctUntilChanged(),
        takeUntil(this.destroy$)
      )
      .subscribe((query) => {
        if (!query) {
          this.suggestions = [];
          this.showSuggestions = false;
          return;
        }

        this.stockService.searchSymbols(query, 8).subscribe({
          next: (res) => {
            this.suggestions = Array.isArray(res?.results) ? res.results : [];
            this.showSuggestions = this.suggestions.length > 0;
          },
          error: () => {
            this.suggestions = [];
            this.showSuggestions = false;
          }
        });
      });

    // The theme initialization logic is now handled within ThemeService
    // const savedTheme = localStorage.getItem('theme');
    // if (savedTheme === 'light') {
    //   this.isDarkTheme = false;
    //   document.documentElement.classList.remove('dark');
    // } else {
    //   this.isDarkTheme = true;
    //   document.documentElement.classList.add('dark');
    // }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onSearchInput(): void {
    const query = this.searchQuery.trim().toUpperCase();
    if (!query) {
      this.suggestions = [];
      this.showSuggestions = false;
      return;
    }
    this.searchSubject.next(query);
  }

  submitSearch(): void {
    const symbol = (this.suggestions[0]?.symbol || this.searchQuery).trim().toUpperCase();
    if (!symbol) return;
    this.navigateToStock(symbol);
  }

  selectSuggestion(symbol: string): void {
    this.navigateToStock(symbol);
  }

  hideSuggestions(): void {
    setTimeout(() => {
      this.showSuggestions = false;
    }, 150);
  }

  private navigateToStock(symbol: string): void {
    const normalized = symbol.trim().toUpperCase();
    if (!normalized) return;
    this.searchQuery = normalized;
    this.suggestions = [];
    this.showSuggestions = false;
    this.router.navigate(['/stocks', normalized]);
  }

  toggleTheme(): void {
    this.themeService.toggleTheme();
  }

  get showHeader(): boolean {
    return this.isVisible && !this.isVideoPlaying;
  }

  @HostListener('window:scroll', [])
  onWindowScroll() {
    const currentScrollY = window.pageYOffset || document.documentElement.scrollTop;

    // Threshold of 60px before triggering header hide logic
    if (currentScrollY > 60) {
      if (currentScrollY > this.lastScrollY) {
        // Scrolling down
        this.isVisible = false;
      } else {
        // Scrolling up
        this.isVisible = true;
      }
    } else {
      // At the top
      this.isVisible = true;
    }

    this.lastScrollY = currentScrollY;
  }

  logout(): void {
    this.authService.logout();
  }
}
