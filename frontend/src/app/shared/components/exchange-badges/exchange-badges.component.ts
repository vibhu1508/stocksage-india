import { Component, Input } from '@angular/core';

/** NSE / BSE pills for where a stock trades (plus INDEX for indices); pushes itself to the right of a flex row. */
@Component({
  selector: 'app-exchange-badges',
  standalone: true,
  template: `
    @if (kind === 'index') {
      <span class="badge index">INDEX</span>
    }
    @for (x of exchanges; track x) {
      <span class="badge" [class.nse]="x === 'NSE'" [class.bse]="x === 'BSE'">{{ x }}</span>
    }
  `,
  styles: [`
    :host { display: inline-flex; flex-shrink: 0; gap: 0.25rem; margin-left: auto; }
    .badge {
      padding: 0.08rem 0.38rem;
      border: 1px solid currentColor;
      border-radius: 0.3rem;
      font-size: 0.62rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      line-height: 1.3;
    }
    .nse { color: #2563eb; background: rgb(37 99 235 / 0.1); }
    .bse { color: #d97706; background: rgb(217 119 6 / 0.1); }
    .index { color: #7c3aed; background: rgb(124 58 237 / 0.1); }
  `],
})
export class ExchangeBadgesComponent {
  @Input() exchanges: string[] = [];
  @Input() kind?: 'index';
}
