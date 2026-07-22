import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

import { AuthService } from './auth.service';

export interface HoldingConfirm {
  symbol: string;
  quantity: number;
  avg_price: number;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  /** True while the assistant reply is still streaming in. */
  streaming?: boolean;
  /** Name of the tool currently running (shown as an activity chip). */
  tool?: string | null;
  /** Portfolio add awaiting the user's confirmation (renders a confirm card). */
  confirm?: HoldingConfirm | null;
  /** Set once the user has confirmed/cancelled, so the card buttons disable. */
  confirmed?: boolean;
}

interface ChatEvent {
  type: 'token' | 'tool' | 'done' | 'error' | 'confirm_request';
  text?: string;
  name?: string;
  detail?: string;
  holding?: HoldingConfirm;
}

/**
 * Talks to the StockSage AI assistant over `WS /api/chat/ws` and exposes the
 * running message list. Read-only market tools for now; the socket is opened
 * lazily on the first message and reused.
 */
@Injectable({ providedIn: 'root' })
export class AiChatService {
  private ws?: WebSocket;
  private socketPromise?: Promise<WebSocket>;
  private pendingConfirm: HoldingConfirm | null = null;

  private readonly messagesSubject = new BehaviorSubject<ChatMessage[]>([]);
  readonly messages$ = this.messagesSubject.asObservable();

  constructor(private auth: AuthService) {}

  get messages(): ChatMessage[] {
    return this.messagesSubject.value;
  }

  get isBusy(): boolean {
    const last = this.messages[this.messages.length - 1];
    return !!last && last.role === 'assistant' && !!last.streaming;
  }

  async send(text: string): Promise<void> {
    const trimmed = text.trim();
    if (!trimmed || this.isBusy) return;

    this.push({ role: 'user', text: trimmed });
    this.push({ role: 'assistant', text: '', streaming: true, tool: null });

    try {
      const ws = await this.ensureSocket();
      ws.send(JSON.stringify({ message: trimmed }));
    } catch {
      this.finishWithError('Could not connect to the assistant. Please try again.');
    }
  }

  reset(): void {
    this.messagesSubject.next([]);
  }

  // ── internals ──

  private buildWsUrl(): string {
    const backend = new URL(import.meta.env.NG_APP_BACKEND);
    const proto = backend.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = this.auth.getToken();
    const query = token ? `?token=${encodeURIComponent(token)}` : '';
    return `${proto}//${backend.host}/api/chat/ws${query}`;
  }

  /** Confirm a pending portfolio add (the write happens only now). */
  async confirmHolding(msg: ChatMessage): Promise<void> {
    if (!msg.confirm || msg.confirmed) return;
    this.markConfirmed(msg);
    this.push({ role: 'assistant', text: '', streaming: true, tool: null });
    await this.sendAction({ action: 'confirm_holding', holding: msg.confirm });
  }

  /** Cancel a pending portfolio add. */
  async cancelHolding(msg: ChatMessage): Promise<void> {
    if (!msg.confirm || msg.confirmed) return;
    this.markConfirmed(msg);
    this.push({ role: 'assistant', text: '', streaming: true, tool: null });
    await this.sendAction({ action: 'cancel_holding' });
  }

  private async sendAction(payload: Record<string, unknown>): Promise<void> {
    try {
      const ws = await this.ensureSocket();
      ws.send(JSON.stringify(payload));
    } catch {
      this.finishWithError('Could not connect to the assistant. Please try again.');
    }
  }

  private markConfirmed(target: ChatMessage): void {
    const msgs = this.messages;
    const i = msgs.indexOf(target);
    if (i >= 0) {
      const next = [...msgs];
      next[i] = { ...msgs[i], confirmed: true };
      this.messagesSubject.next(next);
    }
  }

  private ensureSocket(): Promise<WebSocket> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return Promise.resolve(this.ws);
    if (this.socketPromise) return this.socketPromise;

    this.socketPromise = new Promise<WebSocket>((resolve, reject) => {
      let socket: WebSocket;
      try {
        socket = new WebSocket(this.buildWsUrl());
      } catch (err) {
        this.socketPromise = undefined;
        reject(err);
        return;
      }
      socket.onopen = () => {
        this.ws = socket;
        resolve(socket);
      };
      socket.onmessage = (e) => {
        try {
          this.handleEvent(JSON.parse(e.data) as ChatEvent);
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onerror = () => {
        if (!this.ws) {
          this.socketPromise = undefined;
          reject(new Error('WebSocket error'));
        }
      };
      socket.onclose = () => {
        this.ws = undefined;
        this.socketPromise = undefined;
        if (this.isBusy) this.finishWithError('Connection closed. Please try again.');
      };
    });
    return this.socketPromise;
  }

  private handleEvent(ev: ChatEvent): void {
    switch (ev.type) {
      case 'token':
        this.updateLastAssistant((m) => ({ ...m, text: m.text + (ev.text ?? ''), tool: null }));
        break;
      case 'tool':
        this.updateLastAssistant((m) => ({ ...m, tool: ev.name ?? null }));
        break;
      case 'confirm_request':
        this.pendingConfirm = ev.holding ?? null;
        break;
      case 'done': {
        const confirm = this.pendingConfirm;
        this.pendingConfirm = null;
        this.updateLastAssistant((m) => ({ ...m, streaming: false, tool: null, confirm: confirm ?? m.confirm }));
        break;
      }
      case 'error':
        this.finishWithError(ev.detail ?? 'Something went wrong.');
        break;
    }
  }

  private finishWithError(message: string): void {
    this.updateLastAssistant((m) => ({
      ...m,
      text: m.text || message,
      streaming: false,
      tool: null,
    }));
  }

  private push(msg: ChatMessage): void {
    this.messagesSubject.next([...this.messages, msg]);
  }

  private updateLastAssistant(fn: (m: ChatMessage) => ChatMessage): void {
    const msgs = this.messages;
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'assistant') {
        const next = [...msgs];
        next[i] = fn(msgs[i]);
        this.messagesSubject.next(next);
        return;
      }
    }
  }
}
