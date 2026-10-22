import { Component, Input, OnChanges, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';

import { CompanyLogoService } from '../../../core/services/company-logo.service';

/** A company's logo on a light tile, or its first letter when there is no logo. Decorative:
 *  the symbol is always shown next to it, so it is hidden from screen readers. */
@Component({
  selector: 'app-company-logo',
  standalone: true,
  template: `
    <span class="logo" [class.letter]="!url" [style.width.px]="size" [style.height.px]="size" aria-hidden="true">
      @if (url) {
        <img [src]="url" [width]="size" [height]="size" alt="" loading="lazy" decoding="async" (error)="onError()" />
      } @else {
        <span [style.font-size.px]="size * 0.46">{{ initial }}</span>
      }
    </span>
  `,
  styles: [`
    :host { display: inline-flex; flex-shrink: 0; }
    .logo {
      display: inline-grid;
      place-items: center;
      overflow: hidden;
      border-radius: 28%;
      background: #fff; /* dark wordmarks stay visible in the dark theme */
      box-shadow: inset 0 0 0 1px hsl(var(--border));
    }
    .logo img { width: 100%; height: 100%; object-fit: contain; }
    .logo.letter {
      background: hsl(var(--muted));
      color: hsl(var(--foreground));
      font-weight: 800;
      line-height: 1;
    }
  `],
})
export class CompanyLogoComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) symbol = '';
  @Input() size = 28;

  url: string | null = null;
  private sub?: Subscription;

  constructor(private logos: CompanyLogoService) {}

  get initial(): string {
    return (this.symbol.replace(/^BSE:/, '').trim()[0] || '?').toUpperCase();
  }

  ngOnChanges(): void {
    this.sub?.unsubscribe();
    this.url = null;
    // Request twice the shown size so logos stay sharp on high-density screens.
    this.sub = this.logos.logoUrl(this.symbol, this.size > 32 ? 128 : 64).subscribe((url) => (this.url = url));
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  onError(): void {
    if (this.url) this.logos.markMissing(this.url);
    this.url = null;
  }
}
