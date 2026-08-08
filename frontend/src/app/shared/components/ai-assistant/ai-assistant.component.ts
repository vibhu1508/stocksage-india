import { AfterViewChecked, Component, ElementRef, HostListener, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LucideAngularModule } from 'lucide-angular';
import { marked } from 'marked';
import { Subscription } from 'rxjs';

marked.setOptions({ breaks: true, gfm: true });

import { AiAssistantService } from '../../../core/services/ai-assistant.service';
import { AiChatService } from '../../../core/services/ai-chat.service';
import { VoiceService } from '../../../core/services/voice.service';
import { SageIconComponent } from '../sage-icon/sage-icon.component';
import { VoiceWaveComponent } from './voice-wave.component';

/**
 * StockSage AI assistant panel — live chat over WS /api/chat/ws.
 * Shows the compliance disclaimer at the top of every session and a per-message
 * ⓘ tooltip (EN + HI). Voice is added in a later phase.
 */
@Component({
  selector: 'app-ai-assistant',
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule, SageIconComponent, VoiceWaveComponent],
  template: `
    @if (aiAssistant.isOpen$ | async) {
    <div class="fixed inset-0 z-[70]">
      <div class="absolute inset-0 bg-background/70 backdrop-blur-sm" (click)="aiAssistant.close()"></div>

      <aside
        class="absolute right-0 top-0 flex h-full w-full flex-col border-l border-border bg-card shadow-2xl sm:w-[440px]"
        [style.width.px]="isDesktop ? panelWidth : null"
        [style.animation]="resizing ? 'none' : 'sage-slide-in .22s ease-out'"
      >
        <!-- resize handle (desktop) -->
        @if (isDesktop) {
        <div (mousedown)="startResize($event)" title="Drag to resize"
          class="group/resize absolute left-0 top-0 z-30 flex h-full w-2 -translate-x-1/2 cursor-ew-resize items-center justify-center">
          <div class="h-full w-px bg-border transition-colors group-hover/resize:bg-primary/60" [class.bg-primary]="resizing"></div>
        </div>
        }
        <!-- header -->
        <div class="flex items-center gap-3 border-b border-border px-4 py-3">
          <span class="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary ring-1 ring-primary/25">
            <app-sage-icon [size]="22"></app-sage-icon>
          </span>
          <div class="leading-tight">
            <div class="text-sm font-semibold text-foreground">StockSage AI</div>
            <div class="text-[11px] text-muted-foreground">Your market guide · आपका मार्गदर्शक</div>
          </div>
          <button type="button" (click)="toggleVoiceReplies()"
            [title]="voiceReplies ? 'Voice replies on' : 'Voice replies off'"
            [disabled]="!voice.ttsSupported"
            class="ml-auto flex h-8 w-8 items-center justify-center rounded-md transition-colors hover:bg-muted disabled:opacity-40"
            [class.text-primary]="voiceReplies" [class.text-muted-foreground]="!voiceReplies">
            <lucide-icon [name]="voiceReplies ? 'volume-2' : 'volume-x'" [size]="16"></lucide-icon>
          </button>
          <button type="button" (click)="chat.reset()" title="New chat"
            class="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
            <lucide-icon name="refresh-cw" [size]="16"></lucide-icon>
          </button>
          <button type="button" (click)="aiAssistant.close()" aria-label="Close assistant"
            class="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
            <lucide-icon name="x" [size]="18"></lucide-icon>
          </button>
        </div>

        <!-- messages -->
        <div #scrollBox (scroll)="onScroll()" class="relative flex-1 space-y-3 overflow-y-auto p-4">
          <!-- session disclaimer -->
          <div class="space-y-2 rounded-xl border border-border bg-background/60 p-3 text-[11px] leading-relaxed text-muted-foreground">
            <p>{{ disclaimerEn }}</p>
            <p>{{ disclaimerHi }}</p>
          </div>

          @if ((chat.messages$ | async)?.length === 0) {
          <div class="flex flex-col items-center rounded-xl border border-dashed border-border p-6 text-center">
            <app-sage-icon [size]="42" class="mb-3 text-primary/70"></app-sage-icon>
            <p class="text-sm font-medium text-foreground">Namaskar! Swagat hai aapka StockSage AI mein!</p>
            <p class="mt-1 text-xs text-muted-foreground">English · हिंदी · Hinglish — "how is the market?", "RELIANCE ka price?"</p>
          </div>
          }

          @for (m of (chat.messages$ | async); track $index) {
            @if (m.role === 'user') {
            <div class="flex justify-end">
              <div class="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">
                {{ m.text }}
              </div>
            </div>
            } @else {
            <div class="flex items-start gap-2">
              <span class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary ring-1 ring-primary/20">
                <app-sage-icon [size]="16"></app-sage-icon>
              </span>
              <div class="group relative max-w-[85%] rounded-2xl rounded-tl-sm border border-border bg-background px-3.5 py-2 text-sm text-foreground">
                @if (m.tool) {
                  <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span class="sage-dot"></span>{{ toolLabel(m.tool) }}
                  </span>
                } @else if (m.streaming && !m.text) {
                  <span class="flex gap-1 py-1">
                    <span class="sage-dot"></span><span class="sage-dot" style="animation-delay:.15s"></span><span class="sage-dot" style="animation-delay:.3s"></span>
                  </span>
                } @else {
                  <!-- formatted while streaming too, so asterisks never show -->
                  <div class="sage-md" [innerHTML]="renderMarkdown(m.text, m.streaming)"></div>
                }

                <!-- per-message bilingual disclaimer (ⓘ) -->
                @if (!m.streaming && m.text) {
                <span tabindex="0" role="button" aria-label="Disclaimer"
                  class="group/info relative ml-1 inline-flex translate-y-0.5 cursor-help text-muted-foreground/60 hover:text-primary">
                  <lucide-icon name="alert-circle" [size]="13"></lucide-icon>
                  <span class="pointer-events-none absolute bottom-full right-0 z-20 mb-1.5 hidden w-60 max-w-[75vw] rounded-lg border border-border bg-card p-2.5 text-[10px] leading-snug text-muted-foreground shadow-xl group-hover/info:block">
                    <span class="block">{{ disclaimerEn }}</span>
                    <span class="mt-1.5 block">{{ disclaimerHi }}</span>
                  </span>
                </span>
                }
              </div>
            </div>
            }
          }
        </div>

        <!-- jump back to live output (only while reading history) -->
        @if (!pinnedToBottom) {
        <div class="pointer-events-none relative">
          <button type="button" (click)="scrollToLatest()"
            class="pointer-events-auto absolute -top-11 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-[11px] font-medium text-foreground shadow-lg transition-colors hover:bg-muted">
            <lucide-icon name="arrow-down" [size]="13"></lucide-icon>
            Jump to latest
          </button>
        </div>
        }

        <!-- input -->
        <div class="border-t border-border p-3">
          @if (voice.recording$ | async) {
          <!-- recording: live waveform + a clear Stop button -->
          <div class="flex items-center gap-2 rounded-xl border border-primary/30 bg-primary/5 px-3 py-2">
            <button type="button" (click)="cancelMic()" title="Cancel"
              class="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted">
              <lucide-icon name="x" [size]="16"></lucide-icon>
            </button>
            <app-voice-wave class="flex-1" [voice]="voice"></app-voice-wave>
            <button type="button" (click)="toggleMic()" title="Stop & send"
              class="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90">
              <lucide-icon name="square" [size]="13"></lucide-icon>
              Stop
            </button>
          </div>
          } @else {
          <div class="flex items-end gap-2 rounded-xl border border-border bg-background px-3 py-2 focus-within:ring-1 focus-within:ring-primary/40">
            <input
              [(ngModel)]="draft"
              (keydown.enter)="onSend()"
              [disabled]="chat.isBusy"
              type="text"
              [placeholder]="(voice.transcribing$ | async) ? 'Transcribing…' : 'Ask about the market… (EN / हिंदी / Hinglish)'"
              class="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-60"
            />
            <button type="button" (click)="toggleMic()"
              [disabled]="!voice.sttSupported || chat.isBusy || (voice.transcribing$ | async)"
              [title]="voice.sttSupported ? 'Speak' : 'Voice input not supported in this browser'"
              class="flex h-7 w-7 items-center justify-center rounded-md transition-colors hover:bg-muted disabled:opacity-40"
              [class.text-primary]="voice.transcribing$ | async"
              [class.animate-pulse]="voice.transcribing$ | async"
              [class.text-muted-foreground]="!(voice.transcribing$ | async)">
              <lucide-icon name="mic" [size]="17"></lucide-icon>
            </button>
            <button type="button" (click)="onSend()" [disabled]="!draft.trim() || chat.isBusy" aria-label="Send"
              class="flex h-7 w-7 items-center justify-center rounded-md text-primary transition-colors hover:bg-primary/10 disabled:opacity-40">
              <lucide-icon name="send" [size]="17"></lucide-icon>
            </button>
          </div>
          }
          @if (voiceHint) {
          <p class="mt-2 text-center text-[10px] text-primary">{{ voiceHint }}</p>
          } @else {
          <p class="mt-2 text-center text-[10px] text-muted-foreground">
            Market information &amp; education only — not financial advice.
          </p>
          }
        </div>
      </aside>

      @if (resizing) {
      <div class="fixed inset-0 z-[80] cursor-ew-resize"></div>
      }
    </div>
    }
  `,
  styles: [`
    @keyframes sage-slide-in {
      from { transform: translateX(24px); opacity: 0; }
      to   { transform: translateX(0);    opacity: 1; }
    }
    .sage-dot {
      display: inline-block; width: 6px; height: 6px; border-radius: 999px;
      background: hsl(var(--primary)); animation: sage-bounce .9s ease-in-out infinite;
    }
    @keyframes sage-bounce {
      0%, 80%, 100% { transform: translateY(0); opacity: .5; }
      40% { transform: translateY(-4px); opacity: 1; }
    }
    :host ::ng-deep .sage-md > *:first-child { margin-top: 0; }
    :host ::ng-deep .sage-md > *:last-child { margin-bottom: 0; }
    :host ::ng-deep .sage-md p { margin: 0 0 .5rem; }
    :host ::ng-deep .sage-md strong { font-weight: 600; }
    :host ::ng-deep .sage-md em { font-style: italic; }
    :host ::ng-deep .sage-md ul,
    :host ::ng-deep .sage-md ol { margin: .35rem 0 .5rem; padding-left: 1.15rem; }
    :host ::ng-deep .sage-md ul { list-style: disc; }
    :host ::ng-deep .sage-md ol { list-style: decimal; }
    :host ::ng-deep .sage-md li { margin: .2rem 0; }
    :host ::ng-deep .sage-md a { color: hsl(var(--primary)); text-decoration: underline; }
    :host ::ng-deep .sage-md h1,
    :host ::ng-deep .sage-md h2,
    :host ::ng-deep .sage-md h3 { font-weight: 600; margin: .4rem 0 .3rem; font-size: 1em; }
    :host ::ng-deep .sage-md code { background: hsl(var(--muted)); padding: .05rem .3rem; border-radius: .25rem; font-size: .85em; }
  `],
})
export class AiAssistantComponent implements AfterViewChecked, OnInit, OnDestroy {
  @ViewChild('scrollBox') private scrollBox?: ElementRef<HTMLElement>;
  draft = '';

  /** Memoised markdown renders, keyed by source text. */
  private readonly mdCache = new Map<string, string>();

  // ── Scroll following ──
  /** False once the user scrolls up to read history; new output stops chasing them. */
  pinnedToBottom = true;
  private readonly pinThresholdPx = 80;

  // ── Voice ──
  /** When on, assistant replies are read aloud. */
  voiceReplies = false;
  voiceHint = '';
  private msgSub?: Subscription;
  private lastSpoken = '';
  private hintTimer: ReturnType<typeof setTimeout> | undefined;

  // ── Resizable panel (desktop) ──
  panelWidth = 440;
  isDesktop = true;
  resizing = false;
  private readonly minWidth = 340;
  private readonly widthKey = 'sage-chat-width';
  private startX = 0;
  private startWidth = 0;

  readonly disclaimerEn =
    'StockSage AI provides market information and education only — not financial advice. ' +
    'We do not recommend buying or selling any security. Please consult your financial advisor before making any decisions.';

  readonly disclaimerHi =
    'StockSage AI केवल बाज़ार की जानकारी और शिक्षा देता है — यह वित्तीय सलाह नहीं है। ' +
    'हम किसी भी शेयर को खरीदने या बेचने की सलाह नहीं देते। कोई भी निर्णय लेने से पहले कृपया अपने वित्तीय सलाहकार से परामर्श करें।';

  constructor(
    public aiAssistant: AiAssistantService,
    public chat: AiChatService,
    public voice: VoiceService,
  ) {}

  ngOnInit(): void {
    const saved = Number(localStorage.getItem(this.widthKey));
    if (saved && saved >= this.minWidth) this.panelWidth = saved;
    this.updateIsDesktop();

    // Read out each completed assistant reply when voice replies are on.
    this.msgSub = this.chat.messages$.subscribe((msgs) => {
      const last = msgs[msgs.length - 1];
      if (!last || last.role !== 'assistant') return;
      if (last.streaming) return;
      if (!this.voiceReplies || !last.text || last.text === this.lastSpoken) return;
      this.lastSpoken = last.text;
      this.voice.speak(last.text);
    });
  }

  ngOnDestroy(): void {
    this.msgSub?.unsubscribe();
    this.voice.stopSpeaking();
    this.voice.cancelRecording();
  }

  /** Track whether the user is reading history, so we don't yank them to the bottom. */
  onScroll(): void {
    const el = this.scrollBox?.nativeElement;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    this.pinnedToBottom = distanceFromBottom <= this.pinThresholdPx;
  }

  scrollToLatest(): void {
    const el = this.scrollBox?.nativeElement;
    if (!el) return;
    this.pinnedToBottom = true;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }

  ngAfterViewChecked(): void {
    // Only follow new output while the user is already at the bottom. Scrolling
    // unconditionally here made it impossible to read earlier messages, because
    // this hook runs after EVERY change-detection pass.
    if (!this.pinnedToBottom) return;
    const el = this.scrollBox?.nativeElement;
    if (el) el.scrollTop = el.scrollHeight;
  }

  @HostListener('window:resize')
  onWindowResize(): void {
    this.updateIsDesktop();
    // Keep the panel within bounds if the window shrank.
    this.panelWidth = Math.min(this.panelWidth, this.maxWidth);
  }

  private updateIsDesktop(): void {
    this.isDesktop = window.innerWidth >= 640;
  }

  private get maxWidth(): number {
    return Math.min(900, window.innerWidth - 48);
  }

  startResize(event: MouseEvent): void {
    event.preventDefault();
    this.resizing = true;
    this.startX = event.clientX;
    this.startWidth = this.panelWidth;
    document.addEventListener('mousemove', this.onResizeMove);
    document.addEventListener('mouseup', this.onResizeEnd);
  }

  private readonly onResizeMove = (event: MouseEvent): void => {
    if (!this.resizing) return;
    // Handle is on the panel's left edge; dragging left widens the panel.
    const next = this.startWidth + (this.startX - event.clientX);
    this.panelWidth = Math.max(this.minWidth, Math.min(this.maxWidth, next));
  };

  private readonly onResizeEnd = (): void => {
    this.resizing = false;
    document.removeEventListener('mousemove', this.onResizeMove);
    document.removeEventListener('mouseup', this.onResizeEnd);
    localStorage.setItem(this.widthKey, String(Math.round(this.panelWidth)));
  };

  onSend(): void {
    const text = this.draft;
    this.draft = '';
    this.voice.stopSpeaking();
    // Sending is an explicit "I want to see what happens next".
    this.pinnedToBottom = true;
    this.chat.send(text);
  }

  async toggleMic(): Promise<void> {
    if (!this.voice.sttSupported) {
      this.showVoiceHint('Voice input isn’t supported in this browser.');
      return;
    }
    if (this.voice.recording$.value) {
      const text = await this.voice.stopRecording();
      if (text) {
        this.draft = text;
        this.onSend();
      } else {
        // Distinguish "server has no voice" from "I couldn't hear you".
        this.showVoiceHint(
          this.voice.unavailableReason || 'I didn’t catch that — please try again.',
        );
      }
      return;
    }
    this.voiceHint = '';
    await this.voice.startRecording((msg) => this.showVoiceHint(msg));
  }

  /** Discard the recording without transcribing/sending. */
  cancelMic(): void {
    this.voice.cancelRecording();
  }

  private showVoiceHint(msg: string): void {
    this.voiceHint = msg;
    clearTimeout(this.hintTimer);
    this.hintTimer = setTimeout(() => { this.voiceHint = ''; }, 6000);
  }

  toggleVoiceReplies(): void {
    this.voiceReplies = !this.voiceReplies;
    if (!this.voiceReplies) this.voice.stopSpeaking();
  }

  /** Render assistant markdown → HTML (Angular sanitizes the [innerHTML] output). */
  renderMarkdown(text: string, streaming = false): string {
    const src = streaming ? this.closeOpenMarkers(text ?? '') : (text ?? '');

    // The template re-invokes this on every change-detection pass, so memoise —
    // otherwise a streaming reply re-parses the whole message on each token.
    const cached = this.mdCache.get(src);
    if (cached !== undefined) return cached;

    let html: string;
    try {
      html = marked.parse(src, { async: false }) as string;
    } catch {
      html = src;
    }
    if (this.mdCache.size > 60) this.mdCache.clear();
    this.mdCache.set(src, html);
    return html;
  }

  /**
   * Markdown streams in a token at a time, so a bold run reads as "**Reliance"
   * until its closing "**" lands. Speculatively close any open delimiter so text
   * appears already formatted, instead of flashing raw asterisks at the reader.
   */
  private closeOpenMarkers(input: string): string {
    let t = input;

    // Unterminated code fence: close it; nothing inside needs further balancing.
    if (((t.match(/```/g) || []).length) % 2 === 1) return `${t}\n\`\`\``;

    // A delimiter still being typed — drop it rather than show a stray character.
    t = t.replace(/(?:\*{1,3}|_{1,2}|`)$/, '');

    // Close what's still open: inline code, then bold, then italic.
    if (((t.match(/`/g) || []).length) % 2 === 1) t += '`';
    if (((t.match(/\*\*/g) || []).length) % 2 === 1) t += '**';
    const singleStars = (t.replace(/\*\*/g, '').match(/\*/g) || []).length;
    if (singleStars % 2 === 1) t += '*';

    return t;
  }

  toolLabel(tool: string): string {
    switch (tool) {
      case 'get_market_overview': return 'Checking the market…';
      case 'get_top_movers': return 'Finding top movers…';
      case 'get_stock_price': return 'Fetching the price…';
      case 'get_announcements': return 'Reading announcements…';
      default: return 'Working…';
    }
  }
}
