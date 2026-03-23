import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class ThemeService {
  private isDarkThemeSource = new BehaviorSubject<boolean>(true);
  isDarkTheme$ = this.isDarkThemeSource.asObservable();

  constructor() {
    const savedTheme = localStorage.getItem('theme');
    const isDark = savedTheme !== 'light';
    this.setTheme(isDark);
  }

  toggleTheme(): void {
    this.setTheme(!this.isDarkThemeSource.value);
  }

  private setTheme(isDark: boolean): void {
    this.isDarkThemeSource.next(isDark);
    if (isDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }

  get isDark(): boolean {
    return this.isDarkThemeSource.value;
  }
}
