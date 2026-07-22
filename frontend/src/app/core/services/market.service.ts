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

export interface MarketSessionStatus {
  market_status: string;
  is_open: boolean;
  is_trading_day: boolean;
  reason: string;
  timestamp: string;
}

export interface TickerIndex {
  symbol: string;
  value: number;
  change: number;
  pct_change: number;
  up: boolean;
}

export interface IndicesResponse {
  market_status: string;
  indices: TickerIndex[];
  timestamp: string;
}

@Injectable({
  providedIn: 'root'
})
export class MarketService {
  private apiUrl = `${import.meta.env.NG_APP_BACKEND}/api/market`;
  private learnUrl = `${import.meta.env.NG_APP_BACKEND}/api/learn`;

  constructor(private http: HttpClient) { }

  getLiveData(): Observable<MarketData> {
    return this.http.get<MarketData>(`${this.apiUrl}/live`);
  }

  /** Live index snapshot (SENSEX + NSE indices) for the ticker strip. */
  getIndices(): Observable<IndicesResponse> {
    return this.http.get<IndicesResponse>(`${this.apiUrl}/indices`).pipe(
      catchError(() => of({ market_status: '', indices: [], timestamp: new Date().toISOString() }))
    );
  }

  getSessionStatus(): Observable<MarketSessionStatus> {
    return this.http.get<MarketSessionStatus>(`${this.apiUrl}/session-status`).pipe(
      catchError(() => of({
        market_status: this.getLocalMarketStatus(),
        is_open: this.getLocalMarketStatus() === 'Open',
        is_trading_day: this.getLocalMarketStatus() !== 'Closed',
        reason: 'local_fallback',
        timestamp: new Date().toISOString(),
      }))
    );
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

  getTopGainers(): Observable<{ gainers: StockMover[] }> {
    return this.http.get<{ gainers: StockMover[] }>(`${this.apiUrl}/top-stocks`).pipe(
      catchError(() => of({ gainers: [] }))
    );
  }

  getTopLosers(): Observable<{ losers: StockMover[] }> {
    return this.http.get<{ losers: StockMover[] }>(`${this.apiUrl}/top-losers`).pipe(
      catchError(() => of({ losers: [] }))
    );
  }

  getLearnVideos(pageToken: string = ''): Observable<LearnResponse> {
    const params: any = { max_results: '10' };
    if (pageToken) params.page_token = pageToken;
    return this.http.get<LearnResponse>(this.learnUrl + '/videos', { params }).pipe(
      catchError(() => of({ videos: [], nextPageToken: '', totalResults: 0 }))
    );
  }

  searchLearnVideos(q: string, pageToken: string = ''): Observable<LearnResponse> {
    const params: any = { q, max_results: '10' };
    if (pageToken) params.page_token = pageToken;
    return this.http.get<LearnResponse>(this.learnUrl + '/search', { params }).pipe(
      catchError(() => of({ videos: [], nextPageToken: '', totalResults: 0 }))
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
    const istOffset = 5.5 * 60;
    const utcMinutes = now.getUTCHours() * 60 + now.getUTCMinutes();
    const istMinutes = utcMinutes + istOffset;
    const day = now.getUTCDay();

    const adjustedDay = istMinutes >= 1440 ? (day + 1) % 7 : day;
    const adjustedMinutes = istMinutes >= 1440 ? istMinutes - 1440 : istMinutes;

    if (adjustedDay === 0 || adjustedDay === 6) return 'Closed';
    if (adjustedMinutes < 540) return 'Pre-Market';
    if (adjustedMinutes < 555) return 'Pre-Open';
    if (adjustedMinutes <= 930) return 'Open';
    return 'Closed';
  }

  formatIndian(value: string | number): string {
    const num = typeof value === 'string'
      ? parseFloat(value.replace(/,/g, ''))
      : value;
    if (isNaN(num)) return String(value);
    return num.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }
}

export interface StockMover {
  symbol: string;
  price: number;
  change: number;
  pct_change: number;
  volume: number;
}

export interface LearnVideo {
  videoId: string;
  title: string;
  description: string;
  thumbnail: string;
  publishedAt: string;
  channelTitle: string;
  views: number;
  likes: number;
  duration: string;
}

export interface LearnResponse {
  videos: LearnVideo[];
  nextPageToken: string;
  totalResults: number;
}
