import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface SearchResult {
  symbol: string;
  name: string;
  exchange: string;
  type: string;
}

export interface StockQuote {
  symbol: string;
  name: string;
  price: number;
  previousClose: number;
  change: number;
  pctChange: number;
  open: number;
  dayHigh: number;
  dayLow: number;
  volume: number;
  marketCap: number;
  fiftyTwoWeekHigh: number;
  fiftyTwoWeekLow: number;
  exchange: string;
  currency: string;
  logo: string;
}

export interface OHLCVData {
  time: number | string;
  date?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface HistoryResponse {
  symbol: string;
  history: OHLCVData[];
  period: string;
  interval: string;
  count: number;
}

export interface Fundamental {
  symbol: string;
  name: string;
  sector: string;
  industry: string;
  marketCap: number;
  pe: number;
  forwardPe: number;
  eps: number;
  bookValue: number;
  dividendYield: number;
  roe: number;
  debtToEquity: number;
  fiftyTwoWeekHigh: number;
  fiftyTwoWeekLow: number;
  fiftyDayAvg: number;
  twoHundredDayAvg: number;
  beta: number;
  totalRevenue: number;
  revenueGrowth: number;
  profitMargin: number;
  operatingMargin: number;
  website: string;
  description: string;
}

export interface NewsArticle {
  title: string;
  publisher: string;
  link: string;
  publishedAt: number;
  thumbnail: string;
}

export interface OptionEntry {
  strike: number;
  lastPrice: number;
  change: number;
  pctChange: number;
  volume: number;
  openInterest: number;
  impliedVolatility: number;
  inTheMoney: boolean;
}

export interface OptionChain {
  symbol: string;
  expiryDate: string;
  calls: OptionEntry[];
  puts: OptionEntry[];
}

@Injectable({ providedIn: 'root' })
export class ChartService {
  private apiUrl = `${import.meta.env.NG_APP_BACKEND}/api/charts`;

  constructor(private http: HttpClient) { }

  searchTickers(query: string): Observable<{ results: SearchResult[] }> {
    return this.http.get<{ results: SearchResult[] }>(`${this.apiUrl}/search`, {
      params: { q: query }
    });
  }

  getQuote(symbol: string): Observable<StockQuote> {
    return this.http.get<StockQuote>(`${this.apiUrl}/quote`, {
      params: { symbol }
    });
  }

  getHistory(symbol: string, period = '1y', interval = '1d'): Observable<HistoryResponse> {
    return this.http.get<HistoryResponse>(`${this.apiUrl}/history`, {
      params: { symbol, period, interval }
    });
  }

  getIntraday(symbol: string, interval = '1m'): Observable<HistoryResponse> {
    return this.http.get<HistoryResponse>(`${this.apiUrl}/intraday`, {
      params: { symbol, interval }
    });
  }

  getFundamentals(symbol: string): Observable<Fundamental> {
    return this.http.get<Fundamental>(`${this.apiUrl}/fundamentals`, {
      params: { symbol }
    });
  }

  getFinancials(symbol: string, statement = 'income', quarterly = false): Observable<any> {
    return this.http.get(`${this.apiUrl}/financials`, {
      params: { symbol, statement, quarterly: quarterly.toString() }
    });
  }

  getNews(symbol: string): Observable<{ symbol: string; articles: NewsArticle[] }> {
    return this.http.get<{ symbol: string; articles: NewsArticle[] }>(`${this.apiUrl}/news`, {
      params: { symbol }
    });
  }

  getOptionDates(symbol: string): Observable<{ symbol: string; dates: string[] }> {
    return this.http.get<{ symbol: string; dates: string[] }>(`${this.apiUrl}/options/dates`, {
      params: { symbol }
    });
  }

  getOptionChain(symbol: string, date: string): Observable<OptionChain> {
    return this.http.get<OptionChain>(`${this.apiUrl}/options/chain`, {
      params: { symbol, date }
    });
  }
}
