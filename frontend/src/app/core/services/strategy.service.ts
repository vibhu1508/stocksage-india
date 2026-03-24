import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Position {
  segment: string;
  expiry: string;
  strike?: number;
  option_type?: string;
  action: string;
  qty: number;
  entry_price: number;
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

@Injectable({
  providedIn: 'root'
})
export class StrategyService {
  private apiUrl = `${import.meta.env.NG_APP_BACKEND}/api/strategy`;

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
}
