import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

/**
 * Controls the StockSage AI assistant panel (open/close). The sidebar launcher
 * opens it; the app shell renders the panel and reacts to this state.
 */
@Injectable({ providedIn: 'root' })
export class AiAssistantService {
  private readonly openSubject = new BehaviorSubject<boolean>(false);
  readonly isOpen$ = this.openSubject.asObservable();

  get isOpen(): boolean {
    return this.openSubject.value;
  }

  open(): void {
    this.openSubject.next(true);
  }

  close(): void {
    this.openSubject.next(false);
  }

  toggle(): void {
    this.openSubject.next(!this.openSubject.value);
  }
}
