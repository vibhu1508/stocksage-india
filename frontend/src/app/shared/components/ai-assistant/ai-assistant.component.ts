import { AfterViewChecked, Component, ElementRef, HostListener, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LucideAngularModule } from 'lucide-angular';

import { AiAssistantService } from '../../../core/services/ai-assistant.service';
import { AiChatService } from '../../../core/services/ai-chat.service';
import { SageIconComponent } from '../sage-icon/sage-icon.component';

/**
 * StockSage AI assistant panel — live chat over WS /api/chat/ws.
 * Shows the compliance disclaimer at the top of every session and a per-message
 * ⓘ tooltip (EN + HI). Voice is added in a later phase.
 */
@Component({
  selector: 'app-ai-assistant',
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule, SageIconComponent],
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
          <button type="button" (click)="chat.reset()" title="New chat"
            class="ml-auto flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
            <lucide-icon name="refresh-cw" [size]="16"></lucide-icon>
          </button>
          <button type="button" (click)="aiAssistant.close()" aria-label="Close assistant"
            class="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
            <lucide-icon name="x" [size]="18"></lucide-icon>
          </button>
        </div>

        <!-- messages -->
        <div #scrollBox class="flex-1 space-y-3 overflow-y-auto p-4">
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
                  <span class="whitespace-pre-wrap">{{ m.text }}</span>
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

        <!-- input -->
        <div class="border-t border-border p-3">
          <div class="flex items-end gap-2 rounded-xl border border-border bg-background px-3 py-2 focus-within:ring-1 focus-within:ring-primary/40">
            <input
              [(ngModel)]="draft"
              (keydown.enter)="onSend()"
              [disabled]="chat.isBusy"
              type="text"
              placeholder="Ask about the market… (EN / हिंदी / Hinglish)"
              class="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-60"
            />
            <button type="button" title="Voice — coming soon" disabled
              class="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground opacity-50">
              <lucide-icon name="mic" [size]="17"></lucide-icon>
            </button>
            <button type="button" (click)="onSend()" [disabled]="!draft.trim() || chat.isBusy" aria-label="Send"
              class="flex h-7 w-7 items-center justify-center rounded-md text-primary transition-colors hover:bg-primary/10 disabled:opacity-40">
              <lucide-icon name="send" [size]="17"></lucide-icon>
            </button>
          </div>
          <p class="mt-2 text-center text-[10px] text-muted-foreground">
            Market information &amp; education only — not financial advice.
          </p>
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
  `],
})
export class AiAssistantComponent implements AfterViewChecked, OnInit {
  @ViewChild('scrollBox') private scrollBox?: ElementRef<HTMLElement>;
  draft = '';

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

  constructor(public aiAssistant: AiAssistantService, public chat: AiChatService) {}

  ngOnInit(): void {
    const saved = Number(localStorage.getItem(this.widthKey));
    if (saved && saved >= this.minWidth) this.panelWidth = saved;
    this.updateIsDesktop();
  }

  ngAfterViewChecked(): void {
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
    this.chat.send(text);
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
