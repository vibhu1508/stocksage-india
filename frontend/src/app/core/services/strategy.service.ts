import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Position {
  symbol?: string;
  segment: string;
  expiry: string;
  strike?: number;
  option_type?: string;
  action: string;
  qty: number;
  entry_price: number;
  iv?: number;
  delta?: number;
  theta?: number;
  gamma?: number;
  vega?: number;
}

export interface Strategy {
  id?: number;
  name: string;
  symbol: string;
  positions: Position[];
  created_at?: string;
}

export interface UserStrategies {
  live: Strategy[];
  history: Strategy[];
}

export interface PortfolioSyncedHolding {
  id: number;
  symbol: string;
  instrument_type: 'EQUITY' | 'FUTURE' | 'OPTION';
  qty: number;
  lots?: number;
  lot_size?: number;
  avg_price: number;
  invested: number;
  expiry?: string | null;
  strike?: number | null;
  option_type?: 'CE' | 'PE' | null;
  action?: 'BUY' | 'SELL' | null;
  notes?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface PortfolioSyncedResponse {
  count: number;
  total_invested: number;
  holdings: PortfolioSyncedHolding[];
}

export interface YearwiseDataPoint {
  yesterday_chng_per?: number;
  one_week_chng_per?: number;
  one_month_chng_per?: number;
  three_month_chng_per?: number;
  six_month_chng_per?: number;
  one_year_chng_per?: number;
  two_year_chng_per?: number;
  three_year_chng_per?: number;
  five_year_chng_per?: number;
  index_yesterday_chng_per?: number;
  index_one_week_chng_per?: number;
  index_one_month_chng_per?: number;
  index_three_month_chng_per?: number;
  index_six_month_chng_per?: number;
  index_one_year_chng_per?: number;
  index_two_year_chng_per?: number;
  index_three_year_chng_per?: number;
  index_five_year_chng_per?: number;
  index_name?: string;
}

export interface YearwiseDataResponse {
  symbol: string;
  identifier: string;
  count: number;
  data: YearwiseDataPoint[];
}

@Injectable({
  providedIn: 'root'
})
export class StrategyService {
  private apiUrl = `${import.meta.env.NG_APP_BACKEND}/api/strategy`;
  private portfolioApiUrl = `${import.meta.env.NG_APP_BACKEND}/api/portfolio`;

  constructor(private http: HttpClient) { }

  getSymbols(): Observable<{ symbols: string[] }> {
    return this.http.get<{ symbols: string[] }>(`${this.apiUrl}/symbols`);
  }

  getDropdowns(symbol: string): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/dropdowns/${symbol}`);
  }

  getSymbolData(symbol: string): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/symbol-data/${symbol}`);
  }

  getYearwiseData(symbol: string): Observable<YearwiseDataResponse> {
    return this.http.get<YearwiseDataResponse>(`${this.apiUrl}/yearwise-data/${symbol}`);
  }

  getFuturesData(symbol: string, expiry: string, identifier: string): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/futures-data/${symbol}?expiry=${expiry}&identifier=${identifier}`);
  }

  getOptionChain(symbol: string, expiry?: string): Observable<any> {
    let params = new HttpParams();
    if (expiry) {
      params = params.set('expiry', expiry);
    }
    return this.http.get<any>(`${this.apiUrl}/option-chain/${symbol}`, { params });
  }

  saveStrategy(strategy: Strategy): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/save`, strategy);
  }

  getUserStrategies(): Observable<UserStrategies> {
    return this.http.get<UserStrategies>(`${this.apiUrl}/user-strategies`);
  }

  deleteStrategy(id: number): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/strategy/${id}`);
  }

  getPortfolioHoldings(): Observable<PortfolioSyncedResponse> {
    return this.http.get<PortfolioSyncedResponse>(`${this.portfolioApiUrl}/holdings`);
  }
}
