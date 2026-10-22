import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, Subject, Subscription, filter, firstValueFrom } from 'rxjs';

import { DhanChartBootstrapResponse, DhanLiveChartService } from './dhan-live-chart.service';

/** [open time (UTC epoch s), open, high, low, close, volume] */
export type StreamCandle = [number, number, number, number, number, number];

export type MarketStreamMessage =
  | { op: 'snapshot'; key: string; symbol: string; tf: string; candles: StreamCandle[]; last: { price: number; ts: number } | null; market: 'open' | 'closed'; source?: 'rest' }
  | { op: 'delta'; key: string; seq: number; candle: StreamCandle; last: { price: number; ts: number } }
  | { op: 'error'; key: string; detail: string };

/** Last price with day change against the official previous close (backend quote_message). */
export interface LiveQuote {
  op: 'quote';
  key: string;
  price: number;
  ts: number;
  prev_close: number | null;
  change: number | null;
  pct: number | null;
  open?: number;
  high?: number;
  low?: number;
  volume?: number;
}

export interface MarketStreamRequest {
  symbol: string;
  tf: '1' | '5' | '15' | '25' | '60';
  securityId?: string;
  exchangeSegment?: string;
  instrument?: string;
}

const REST_FALLBACK_AFTER_MS = 6000;
const REST_POLL_MS = 60_000;

function restSnapshot(key: string, req: MarketStreamRequest, res: DhanChartBootstrapResponse): MarketStreamMessage {
  const candles: StreamCandle[] = (res.candles || []).map((c) => [c.time, c.open, c.high, c.low, c.close, 0]);
  const last = candles[candles.length - 1];
  return {
    op: 'snapshot', key, symbol: req.symbol, tf: req.tf, candles, source: 'rest',
    last: last ? { price: last[4], ts: last[0] } : null,
    market: 'closed',  // unknown without the stream; pages show the REST state instead
  };
}

/**
 * One socket per tab to the market service (backend/market/service.py), shared by every
 * chart. Each watch() gets a snapshot (about a week of candles) and then live deltas.
 * Auth is a one-time ticket, so the login token never goes in a URL. Reconnects with
 * backoff and re-subscribes, which re-sends snapshots, so a dropped link heals itself.
 */
@Injectable({ providedIn: 'root' })
export class MarketStreamService {
  private readonly url = import.meta.env.NG_APP_MARKET_WS || 'ws://localhost:8001';
  private readonly ticketUrl = `${import.meta.env.NG_APP_BACKEND}/api/market/dhan/stream-ticket`;
  private socket: WebSocket | null = null;
  private connecting: Promise<WebSocket> | null = null;
  private retryMs = 1000;
  private readonly streams = new Map<string, { sub: Record<string, unknown>; out: Subject<MarketStreamMessage | LiveQuote>; refs: number }>();

  constructor(private http: HttpClient, private charts: DhanLiveChartService) {}

  /**
   * Candles for a chart: a snapshot, then deltas for the forming bar. If the market service
   * hasn't answered within a few seconds (down, restarting, unreachable), the same candles are
   * fetched over REST and re-fetched every minute until the stream takes over, so a chart is
   * never left empty. Those snapshots carry source: 'rest'.
   */
  watch(req: MarketStreamRequest): Observable<MarketStreamMessage> {
    const key = `${req.symbol.trim().toUpperCase()}:${req.tf}`;
    const live$ = this.open(key, { op: 'sub', key, ...req }).pipe(
      filter((m): m is MarketStreamMessage => m.op !== 'quote'),
    );

    return new Observable<MarketStreamMessage>((observer) => {
      let streamAnswered = false;
      let timer: ReturnType<typeof setTimeout> | undefined;
      let rest: Subscription | undefined;

      const fetchOverRest = () => {
        rest?.unsubscribe();
        rest = this.charts.getBootstrap({ ...req, timeframe: req.tf }).subscribe({
          next: (res) => {
            if (!streamAnswered) observer.next(restSnapshot(key, req, res));
          },
          error: () => {},  // keep the last candles shown; the next poll or the stream retries
        });
        timer = setTimeout(fetchOverRest, REST_POLL_MS);
      };
      timer = setTimeout(fetchOverRest, REST_FALLBACK_AFTER_MS);

      const sub = live$.subscribe({
        next: (msg) => {
          if (!streamAnswered) {
            streamAnswered = true;
            clearTimeout(timer);
            rest?.unsubscribe();
          }
          observer.next(msg);
        },
        error: (err) => observer.error(err),
      });

      return () => {
        sub.unsubscribe();
        rest?.unsubscribe();
        clearTimeout(timer);
      };
    });
  }

  /** Live price and day change for any symbol or index (e.g. 'NIFTY', 'SENSEX', 'RELIANCE'). */
  watchQuote(symbol: string, ids: Omit<MarketStreamRequest, 'symbol' | 'tf'> = {}): Observable<LiveQuote> {
    const key = `Q:${symbol.trim().toUpperCase()}`;
    return this.open(key, { op: 'quote', key, symbol, ...ids }).pipe(
      filter((m): m is LiveQuote => m.op === 'quote'),
    );
  }

  private open(key: string, subMsg: Record<string, unknown>): Observable<MarketStreamMessage | LiveQuote> {
    return new Observable<MarketStreamMessage | LiveQuote>((observer) => {
      let stream = this.streams.get(key);
      if (!stream) {
        stream = { sub: subMsg, out: new Subject<MarketStreamMessage | LiveQuote>(), refs: 0 };
        this.streams.set(key, stream);
      }
      stream.refs += 1;
      const sub = stream.out.subscribe(observer);
      // Always (re)subscribe so this watcher gets its own snapshot, even if the key is shared.
      void this.send(subMsg);

      return () => {
        sub.unsubscribe();
        const current = this.streams.get(key);
        if (current && --current.refs <= 0) {
          this.streams.delete(key);
          void this.send({ op: 'unsub', key });
        }
      };
    });
  }

  private async send(msg: Record<string, unknown>): Promise<void> {
    try {
      const ws = await this.ensureSocket();
      ws.send(JSON.stringify(msg));
    } catch {
      // The reconnect re-subscribes every active stream.
    }
  }

  private ensureSocket(): Promise<WebSocket> {
    if (this.socket?.readyState === WebSocket.OPEN) return Promise.resolve(this.socket);
    if (this.connecting) return this.connecting;

    this.connecting = (async () => {
      const { ticket } = await firstValueFrom(this.http.post<{ ticket: string }>(this.ticketUrl, {}));
      const ws = new WebSocket(`${this.url}/?ticket=${encodeURIComponent(ticket)}`);
      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        ws.onerror = () => reject(new Error('market socket failed'));
      });
      ws.onmessage = (e: MessageEvent<string>) => this.route(e.data);
      ws.onclose = () => this.onClosed(ws);
      this.socket = ws;
      this.retryMs = 1000;
      return ws;
    })();

    this.connecting.catch(() => this.scheduleReconnect()).finally(() => (this.connecting = null));
    return this.connecting;
  }

  private route(raw: string): void {
    try {
      const msg = JSON.parse(raw) as MarketStreamMessage | LiveQuote;
      this.streams.get(msg.key)?.out.next(msg);
    } catch {
      // ignore malformed frames
    }
  }

  private onClosed(ws: WebSocket): void {
    if (this.socket === ws) this.socket = null;
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    if (this.streams.size === 0) return;
    const delay = this.retryMs + Math.random() * 500;
    this.retryMs = Math.min(this.retryMs * 2, 30_000);
    setTimeout(() => {
      if (this.streams.size === 0 || this.socket || this.connecting) return;
      for (const s of this.streams.values()) void this.send(s.sub);
    }, delay);
  }
}
