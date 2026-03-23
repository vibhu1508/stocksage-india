import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Observable, map, shareReplay } from 'rxjs';

export interface TimeParts {
  hours: string;
  minutes: string;
  seconds: string;
  ampm: string;
}

@Injectable({
  providedIn: 'root'
})
export class ClockService implements OnDestroy {
  private currentTimeSource = new BehaviorSubject<Date>(new Date());
  currentTime$ = this.currentTimeSource.asObservable().pipe(shareReplay(1));

  timeParts$: Observable<TimeParts> = this.currentTime$.pipe(
    map(date => {
      const h = date.getHours();
      const m = date.getMinutes();
      const s = date.getSeconds();
      return {
        hours: (h % 12 || 12).toString().padStart(2, '0'),
        minutes: m.toString().padStart(2, '0'),
        seconds: s.toString().padStart(2, '0'),
        ampm: h >= 12 ? 'PM' : 'AM'
      };
    }),
    shareReplay(1)
  );

  private timer: any;

  constructor() {
    this.timer = setInterval(() => {
      this.currentTimeSource.next(new Date());
    }, 1000);
  }

  ngOnDestroy(): void {
    if (this.timer) {
      clearInterval(this.timer);
    }
  }
}
