import { Component, Input } from '@angular/core';

/**
 * StockSage AI mascot — a serene sage bust rendered as line art.
 * Main strokes use `currentColor` (so it inherits the surrounding text colour like
 * other sidebar icons); the eyes and sash use the app's maroon `--primary` accent.
 */
@Component({
  selector: 'app-sage-icon',
  standalone: true,
  template: `
    <svg
      [attr.width]="size"
      [attr.height]="size"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      [attr.stroke-width]="strokeWidth"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <!-- topknot -->
      <circle cx="12" cy="3.5" r="1.4" />
      <path d="M10.7 5c.8-.5 1.8-.5 2.6 0" />
      <!-- crown / hairline -->
      <path d="M8 9C7.9 6.4 9.6 4.6 12 4.6S16.1 6.4 16 9" />
      <!-- face + beard sweeping to a soft point -->
      <path d="M8 9c-.3 2 0 4 1.2 5.4.9 1 1.8 1.5 2.8 1.5s1.9-.5 2.8-1.5C16 13 16.3 11 16 9" />
      <!-- serene closed eyes (accent) -->
      <path d="M9.6 10q.75.6 1.5 0" style="stroke: hsl(var(--primary))" />
      <path d="M12.9 10q.75.6 1.5 0" style="stroke: hsl(var(--primary))" />
      <!-- shoulders / robe -->
      <path d="M4.7 21c.3-3.2 2.7-5.4 5.5-5.6" />
      <path d="M19.3 21c-.3-3.2-2.7-5.4-5.5-5.6" />
      <!-- sash (accent) -->
      <path d="M9.4 16 16.6 20.8" style="stroke: hsl(var(--primary))" />
    </svg>
  `,
})
export class SageIconComponent {
  @Input() size = 24;
  @Input() strokeWidth = 1.6;
}
