import { Directive, ElementRef, Input, OnChanges, OnDestroy, SimpleChanges } from '@angular/core';

/**
 * Flashes its element when a live number moves: green with ▲ on a rise, red with ▼ on a fall,
 * fading out like a trading terminal (styles: .flash-up / .flash-down in styles.scss).
 * Usage: <span [appFlash]="quote.price">{{ quote.price }}</span>
 */
@Directive({ selector: '[appFlash]', standalone: true })
export class FlashDirective implements OnChanges, OnDestroy {
  @Input('appFlash') value: number | null | undefined;
  private timer?: ReturnType<typeof setTimeout>;

  constructor(private el: ElementRef<HTMLElement>) {}

  ngOnChanges(changes: SimpleChanges): void {
    const change = changes['value'];
    if (!change || change.firstChange) return;
    const prev = Number(change.previousValue);
    const next = Number(change.currentValue);
    if (change.previousValue == null || change.currentValue == null || !Number.isFinite(prev) || !Number.isFinite(next) || prev === next) return;

    const node = this.el.nativeElement;
    node.classList.remove('flash-up', 'flash-down');
    void node.offsetWidth; // restart the animation when moves come back to back
    node.classList.add(next > prev ? 'flash-up' : 'flash-down');
    clearTimeout(this.timer);
    this.timer = setTimeout(() => node.classList.remove('flash-up', 'flash-down'), 900);
  }

  ngOnDestroy(): void {
    clearTimeout(this.timer);
  }
}
