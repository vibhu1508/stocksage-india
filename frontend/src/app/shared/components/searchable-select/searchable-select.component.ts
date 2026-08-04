import {
  Component,
  ElementRef,
  EventEmitter,
  HostListener,
  Input,
  Output,
  ViewChild,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LucideAngularModule } from 'lucide-angular';

/**
 * A dropdown with type-to-filter, for lists too long to scan in a native
 * `<select>` (the F&O tabs pick from ~200 ticker symbols).
 */
@Component({
  selector: 'app-searchable-select',
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule],
  template: `
    <div class="relative" [class.w-full]="true">
      <button
        type="button"
        (click)="toggle()"
        class="flex h-9 w-full items-center justify-between gap-2 rounded-md border border-input bg-background/50 px-3 py-1 text-sm text-foreground shadow-sm transition-colors hover:bg-muted/40 focus:outline-none focus:ring-1 focus:ring-ring"
      >
        <span class="truncate" [class.text-muted-foreground]="!value">
          {{ value || allLabel }}
        </span>
        <lucide-icon
          name="chevron-down"
          [size]="14"
          class="shrink-0 text-muted-foreground transition-transform"
          [class.rotate-180]="open()"
        ></lucide-icon>
      </button>

      @if (open()) {
      <div
        class="absolute z-50 mt-1 w-full min-w-[12rem] overflow-hidden rounded-md border border-border bg-card shadow-lg"
      >
        <div class="border-b border-border p-2">
          <input
            #searchInput
            type="text"
            [ngModel]="query()"
            (ngModelChange)="onQueryChange($event)"
            (keydown)="onKeydown($event)"
            placeholder="Search..."
            class="h-8 w-full rounded-sm border border-input bg-background/50 px-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <ul class="max-h-64 overflow-y-auto py-1 text-sm">
          @if (allowAll && !query()) {
          <li>
            <button
              type="button"
              (click)="select('')"
              class="flex w-full items-center px-3 py-1.5 text-left transition-colors hover:bg-muted"
              [class.bg-muted]="!value"
            >
              {{ allLabel }}
            </button>
          </li>
          } @for (option of filtered(); track option; let i = $index) {
          <li>
            <button
              type="button"
              (click)="select(option)"
              (mouseenter)="highlighted.set(i)"
              class="flex w-full items-center justify-between px-3 py-1.5 text-left transition-colors"
              [class.bg-muted]="i === highlighted()"
              [class.font-semibold]="option === value"
            >
              <span class="truncate">{{ option }}</span>
              @if (option === value) {
              <lucide-icon name="check" [size]="14" class="shrink-0 text-primary"></lucide-icon>
              }
            </button>
          </li>
          } @empty {
          <li class="px-3 py-4 text-center text-muted-foreground">No matches</li>
          }
        </ul>
      </div>
      }
    </div>
  `,
})
export class SearchableSelectComponent {
  @Input() options: string[] = [];
  @Input() value = '';
  /** Shows a reset entry (empty value) at the top of the list. */
  @Input() allowAll = false;
  @Input() allLabel = 'All';

  @Output() valueChange = new EventEmitter<string>();

  readonly open = signal(false);
  readonly query = signal('');
  readonly highlighted = signal(0);

  private optionsSignal = signal<string[]>([]);

  readonly filtered = computed(() => {
    const q = this.query().trim().toLowerCase();
    const all = this.optionsSignal();
    return q ? all.filter(o => o.toLowerCase().includes(q)) : all;
  });

  @ViewChild('searchInput') searchInput?: ElementRef<HTMLInputElement>;

  constructor(private host: ElementRef<HTMLElement>) { }

  ngOnChanges(): void {
    this.optionsSignal.set(this.options ?? []);
  }

  toggle(): void {
    this.open.update(o => !o);
    if (this.open()) {
      this.query.set('');
      this.highlighted.set(Math.max(0, this.filtered().indexOf(this.value)));
      // Focus the filter box once the panel is in the DOM.
      setTimeout(() => this.searchInput?.nativeElement.focus());
    }
  }

  onQueryChange(value: string): void {
    this.query.set(value);
    this.highlighted.set(0);
  }

  select(option: string): void {
    this.open.set(false);
    if (option !== this.value) {
      this.value = option;
      this.valueChange.emit(option);
    }
  }

  onKeydown(event: KeyboardEvent): void {
    const options = this.filtered();
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        this.highlighted.update(i => Math.min(i + 1, options.length - 1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        this.highlighted.update(i => Math.max(i - 1, 0));
        break;
      case 'Enter':
        event.preventDefault();
        if (options[this.highlighted()]) this.select(options[this.highlighted()]);
        break;
      case 'Escape':
        event.preventDefault();
        this.open.set(false);
        break;
    }
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (this.open() && !this.host.nativeElement.contains(event.target as Node)) {
      this.open.set(false);
    }
  }
}
