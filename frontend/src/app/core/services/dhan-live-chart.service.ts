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

export interface DhanDepthLevel {
  price: number;
  quantity: number;
  orders: number;
}

export interface DhanMarketDepthResponse {
  symbol: string;
  identity: DhanChartIdentity;
  source: 'live' | 'cache';
  limit: number;
  buy: DhanDepthLevel[];
  sell: DhanDepthLevel[];
}

@Injectable({
  providedIn: 'root'
})
export class DhanLiveChartService {
  private readonly apiUrl = `${import.meta.env.NG_APP_BACKEND}/api/market/dhan/chart`;
  private readonly backendUrl = `${import.meta.env.NG_APP_BACKEND}`;

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

  getMarketDepth(req: DhanChartRequest, limit = 20): Observable<DhanMarketDepthResponse> {
    const params = this.buildParams(req).set('limit', String(Math.max(1, Math.min(200, limit))));
    return this.http.get<DhanMarketDepthResponse>(`${import.meta.env.NG_APP_BACKEND}/api/market/dhan/quote/depth`, {
      params,
    });
  }

  streamTicks(req: DhanChartRequest): Observable<DhanChartTickResponse> {
    return new Observable<DhanChartTickResponse>((observer) => {
      let socket: WebSocket | null = null;

      try {
        const wsUrl = this.buildWebSocketUrl(req);
        socket = new WebSocket(wsUrl);
      } catch (err) {
        observer.error(err);
        return;
      }

      socket.onmessage = (event: MessageEvent<string>) => {
        try {
          const raw = JSON.parse(event.data) as Record<string, unknown>;
          if (raw['event'] !== 'chart_tick') {
            return;
          }

          const tick: DhanChartTickResponse = {
            identity: {
              symbol: String((raw['identity'] as Record<string, unknown> | undefined)?.['symbol'] ?? req.symbol),
              securityId: String((raw['identity'] as Record<string, unknown> | undefined)?.['securityId'] ?? req.securityId ?? ''),
              exchangeSegment: String((raw['identity'] as Record<string, unknown> | undefined)?.['exchangeSegment'] ?? req.exchangeSegment ?? ''),
              instrument: String((raw['identity'] as Record<string, unknown> | undefined)?.['instrument'] ?? req.instrument ?? ''),
            },
            event: 'chart_tick',
            symbol: String(raw['symbol'] ?? req.symbol),
            timeframe: String(raw['timeframe'] ?? req.timeframe),
            timestamp: Number(raw['timestamp'] ?? 0),
            price: Number(raw['price'] ?? 0),
            source: (String(raw['source'] ?? 'live') as 'live' | 'cache' | 'stale_cache'),
          };

          if (!Number.isFinite(tick.timestamp) || !Number.isFinite(tick.price) || tick.price <= 0) {
            return;
          }

          observer.next(tick);
        } catch {
          // Ignore malformed frames and keep the stream alive.
        }
      };

      socket.onerror = () => {
        observer.error(new Error('WebSocket stream error'));
      };

      socket.onclose = () => {
        observer.complete();
      };

      return () => {
        if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
          socket.close();
        }
      };
    });
  }

  private buildWebSocketUrl(req: DhanChartRequest): string {
    const backend = new URL(this.backendUrl);
    const wsProtocol = backend.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = new URL(`${wsProtocol}//${backend.host}/api/market/dhan/chart/ws`);

    url.searchParams.set('symbol', req.symbol.trim().toUpperCase());
    url.searchParams.set('timeframe', req.timeframe);

    const normalizedSecurityId = (req.securityId || '').trim();
    if (/^\d+$/.test(normalizedSecurityId)) {
      url.searchParams.set('securityId', normalizedSecurityId);
    }
    if (req.exchangeSegment) {
      url.searchParams.set('exchangeSegment', req.exchangeSegment);
    }
    if (req.instrument) {
      url.searchParams.set('instrument', req.instrument);
    }

    return url.toString();
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
