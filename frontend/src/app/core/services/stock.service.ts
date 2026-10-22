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
  /** Where it trades: ['NSE'], ['BSE'] or ['NSE', 'BSE']. */
  exchanges?: string[];
  /** 'index' for indices (key "INDEX:<symbol>"). */
  kind?: 'index';
}

export interface IndexConstituent {
  symbol: string;
  name: string;
  industry: string;
  close: number | null;
  change: number | null;
  pct: number | null;
}

/** /api/stocks/index/{key}: NSE's overview (NSE indices only) and constituents (about 30 NSE indices). */
export interface IndexAnalysis {
  key: string;
  symbol: string;
  name: string;
  exchange: 'NSE' | 'BSE';
  overview: Record<'last' | 'variation' | 'percentChange' | 'open' | 'high' | 'low' | 'previousClose' | 'yearHigh' | 'yearLow'
    | 'pe' | 'pb' | 'dy' | 'advances' | 'declines' | 'unchanged' | 'perChange30d' | 'perChange365d'
    | 'oneWeekAgoVal' | 'oneMonthAgoVal' | 'oneYearAgoVal', number | null> | null;
  constituents: {
    asOf: string | null;
    rows: IndexConstituent[];
    advances: number;
    declines: number;
    unchanged: number;
    industries: Array<{ industry: string; count: number; avgPct: number }>;
  } | null;
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

  getIndexAnalysis(key: string): Observable<IndexAnalysis> {
    return this.http.get<IndexAnalysis>(`${this.apiUrl}/index/${encodeURIComponent(key)}`);
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

