import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export type ChartTimeframe = '1' | '5' | '15' | '60' | 'D';

export interface DhanChartIdentity {
  symbol: string;
  securityId: string;
  exchangeSegment: string;
  instrument: string;
}

export interface DhanChartCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface DhanChartBootstrapResponse {
  symbol: string;
  timeframe: string;
  resolvedTimeframe?: string;
  identity: DhanChartIdentity;
  source: 'live' | 'cache';
  candles: DhanChartCandle[];
}

export interface DhanChartTickResponse {
  identity: DhanChartIdentity;
  event: 'chart_tick';
  symbol: string;
  timeframe: string;
  timestamp: number;
  price: number;
  source: 'live' | 'cache' | 'stale_cache';
}

export interface DhanChartRequest {
  symbol: string;
  timeframe: ChartTimeframe;
  securityId?: string;
  exchangeSegment?: string;
  instrument?: string;
}

@Injectable({
  providedIn: 'root'
})
export class DhanLiveChartService {
  private readonly apiUrl = `${import.meta.env.NG_APP_BACKEND}/api/market/dhan/chart`;

  constructor(private http: HttpClient) {}

  getBootstrap(req: DhanChartRequest): Observable<DhanChartBootstrapResponse> {
    return this.http.get<DhanChartBootstrapResponse>(`${this.apiUrl}/bootstrap`, {
      params: this.buildParams(req),
    });
  }

  getLatestTick(req: DhanChartRequest): Observable<DhanChartTickResponse> {
    return this.http.get<DhanChartTickResponse>(`${this.apiUrl}/latest`, {
      params: this.buildParams(req),
    });
  }

  private buildParams(req: DhanChartRequest): HttpParams {
    let params = new HttpParams()
      .set('symbol', req.symbol)
      .set('timeframe', req.timeframe);

    const normalizedSecurityId = (req.securityId || '').trim();
    const isNumericSecurityId = /^\d+$/.test(normalizedSecurityId);

    // Never pass ISIN-like IDs here; backend can resolve by symbol when securityId is absent.
    if (isNumericSecurityId) params = params.set('securityId', normalizedSecurityId);
    if (req.exchangeSegment) params = params.set('exchangeSegment', req.exchangeSegment);
    if (req.instrument) params = params.set('instrument', req.instrument);

    return params;
  }
}
