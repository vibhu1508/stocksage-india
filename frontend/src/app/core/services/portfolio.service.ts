import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface PortfolioHolding {
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

export interface PortfolioResponse {
  count: number;
  total_invested: number;
  holdings: PortfolioHolding[];
}

export interface AddHoldingPayload {
  symbol: string;
  instrument_type: 'EQUITY' | 'FUTURE' | 'OPTION';
  qty: number;
  lots?: number;
  avg_price: number;
  expiry?: string;
  strike?: number;
  option_type?: 'CE' | 'PE';
  action?: 'BUY' | 'SELL';
  notes?: string;
}

export interface SymbolSuggestion {
  symbol: string;
  name: string;
  series?: string;
  allowed_instruments?: Array<'EQUITY' | 'FUTURE' | 'OPTION'>;
}

export interface SymbolSuggestionResponse {
  query: string;
  type?: 'derivatives' | 'equity' | 'etf';
  count: number;
  results: SymbolSuggestion[];
}

export interface LotSizeResponse {
  symbol: string;
  lot_size: number;
}

export interface DerivativeContractsResponse {
  symbol: string;
  instrument_type: 'FUTURE' | 'OPTION';
  source: 'dhan' | 'nse';
  expiries: string[];
  strikes: number[];
  selected_expiry?: string | null;
}

@Injectable({
  providedIn: 'root'
})
export class PortfolioService {
  private apiUrl = `${import.meta.env.NG_APP_BACKEND}/api/portfolio`;
  private stocksApiUrl = `${import.meta.env.NG_APP_BACKEND}/api/stocks`;

  constructor(private http: HttpClient) {}

  getHoldings(): Observable<PortfolioResponse> {
    return this.http.get<PortfolioResponse>(`${this.apiUrl}/holdings`);
  }

  addHolding(payload: AddHoldingPayload): Observable<{ message: string; holding_id: number }> {
    return this.http.post<{ message: string; holding_id: number }>(`${this.apiUrl}/holdings`, payload);
  }

  deleteHolding(holdingId: number): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.apiUrl}/holdings/${holdingId}`);
  }

  getSymbolSuggestions(
    query: string,
    searchType: 'derivatives' | 'equity' | 'etf' = 'equity'
  ): Observable<SymbolSuggestionResponse> {
    return this.http.get<SymbolSuggestionResponse>(`${this.stocksApiUrl}/nse-global-search`, {
      params: {
        q: query,
        limit: 10,
        type: searchType,
      },
    });
  }

  getLotSize(symbol: string): Observable<LotSizeResponse> {
    return this.http.get<LotSizeResponse>(`${this.apiUrl}/lot-size/${encodeURIComponent(symbol)}`);
  }

  getDerivativeContracts(
    symbol: string,
    instrumentType: 'FUTURE' | 'OPTION',
    expiry?: string
  ): Observable<DerivativeContractsResponse> {
    const params: Record<string, string> = {
      instrument_type: instrumentType,
    };
    if (expiry) {
      params['expiry'] = expiry;
    }

    return this.http.get<DerivativeContractsResponse>(
      `${this.apiUrl}/derivatives/contracts/${encodeURIComponent(symbol)}`,
      {
        params,
      }
    );
  }
}
