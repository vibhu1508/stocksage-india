import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, interval, switchMap, startWith, shareReplay, catchError, of } from 'rxjs';

export interface IndexData {
  name: string;
  value: string;
  change: string;
  pct_change: string;
  high: string;
  low: string;
  open: string;
  prev_close: string;
}

export interface MarketData {
  market_status: string;
  sensex: IndexData | null;
  nifty: IndexData | null;
  timestamp: string;
}

@Injectable({
  providedIn: 'root'
})
export class MarketService {
  private apiUrl = `${import.meta.env.NG_APP_BACKEND}/api/market`;

  constructor(private http: HttpClient) { }

  getLiveData(): Observable<MarketData> {
    return this.http.get<MarketData>(`${this.apiUrl}/live`);
  }

  /**
   * Returns an observable that auto-refreshes every `intervalMs` milliseconds
   */
  getLiveDataStream(intervalMs: number = 10000): Observable<MarketData> {
    return interval(intervalMs).pipe(
      startWith(0),
      switchMap(() => this.getLiveData().pipe(
        catchError(() => of(this.getFallbackData()))
      )),
      shareReplay(1)
    );
  }

  private getFallbackData(): MarketData {
    return {
      market_status: this.getLocalMarketStatus(),
      sensex: null,
      nifty: null,
      timestamp: new Date().toISOString()
    };
  }

  private getLocalMarketStatus(): string {
    const now = new Date();
    // Convert to IST
    const istOffset = 5.5 * 60; // minutes
    const utcMinutes = now.getUTCHours() * 60 + now.getUTCMinutes();
    const istMinutes = utcMinutes + istOffset;
    const day = now.getUTCDay(); // 0=Sun, 6=Sat

    // Adjust day if IST crosses midnight
    const adjustedDay = istMinutes >= 1440 ? (day + 1) % 7 : day;
    const adjustedMinutes = istMinutes >= 1440 ? istMinutes - 1440 : istMinutes;

    if (adjustedDay === 0 || adjustedDay === 6) return 'Closed';
    if (adjustedMinutes < 540) return 'Pre-Market';
    if (adjustedMinutes < 555) return 'Pre-Open';
    if (adjustedMinutes <= 930) return 'Open';
    return 'Closed';
  }

  /**
   * Format a number string to Indian locale (e.g., 1,23,456.78)
   */
  formatIndian(value: string | number): string {
    const num = typeof value === 'string'
      ? parseFloat(value.replace(/,/g, ''))
      : value;
    if (isNaN(num)) return String(value);
    return num.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }
}
