import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface BhavCopyData {
  date: string;
  count: number;
  data: StockData[];
}

export interface StockData {
  TckrSymb: string;
  OpnPric: number;
  HghPric: number;
  LwPric: number;
  ClsPric: number;
  TtlTrdVol: number;
  TtlTrdVal: number;
}

export interface StockComparison {
  date1: string;
  date2: string;
  count: number;
  gainers: ComparisonItem[];
  losers: ComparisonItem[];
  data: ComparisonItem[];
}

export interface ComparisonItem {
  Symbol: string;
  InstrumentName: string;
  OldPrice: number;
  NewPrice: number;
  PctChange: number;
  VolumeRatio: number;
  Volume: number;
}

export interface SymbolSearchResult {
  symbol: string;
  name: string;
}

export interface SearchResponse {
  query: string;
  count: number;
  results: SymbolSearchResult[];
}

export interface LiveSearchResponse {
  date1: string;
  date2: string;
  searched_symbols: string[];
  found_count: number;
  not_found: string[];
  data: ComparisonItem[];
}

@Injectable({
  providedIn: 'root'
})
export class StockService {
  private apiUrl = `${import.meta.env.NG_APP_BACKEND}/api/stocks`;

  constructor(private http: HttpClient) { }

  getSymbols(): Observable<{ symbols: string[] }> {
    return this.http.get<{ symbols: string[] }>(`${this.apiUrl}/symbols`);
  }

  searchSymbols(query: string, limit: number = 10): Observable<SearchResponse> {
    const params = new HttpParams()
      .set('q', query)
      .set('limit', limit.toString());
    return this.http.get<SearchResponse>(`${this.apiUrl}/search`, { params });
  }

  liveSearch(symbols: string, date1: string, date2: string): Observable<LiveSearchResponse> {
    const params = new HttpParams()
      .set('symbols', symbols)
      .set('date1', date1)
      .set('date2', date2);
    return this.http.get<LiveSearchResponse>(`${this.apiUrl}/live-search`, { params });
  }

  getBhavCopy(date: string): Observable<BhavCopyData> {
    return this.http.get<BhavCopyData>(`${this.apiUrl}/bhavcopy/${date}`);
  }

  compareStocks(date1: string, date2: string, symbols?: string): Observable<StockComparison> {
    let params = new HttpParams()
      .set('date1', date1)
      .set('date2', date2);

    if (symbols) {
      params = params.set('symbols', symbols);
    }

    return this.http.get<StockComparison>(`${this.apiUrl}/compare`, { params });
  }
}

