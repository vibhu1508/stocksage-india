import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { of } from 'rxjs';

import { DhanLiveChartService } from './dhan-live-chart.service';
import { MarketStreamMessage, MarketStreamService } from './market-stream.service';

// The market service never answers here (its ticket request stays pending), as when it is down.
describe('MarketStreamService REST fallback', () => {
  let service: MarketStreamService;
  let getBootstrap: jasmine.Spy;

  beforeEach(() => {
    getBootstrap = jasmine.createSpy('getBootstrap').and.returnValue(of({
      symbol: 'RELIANCE', timeframe: '5', identity: {} as any, source: 'live',
      candles: [{ time: 1792659000, open: 1190, high: 1192, low: 1188, close: 1191 }],
    }));
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: DhanLiveChartService, useValue: { getBootstrap } },
      ],
    });
    service = TestBed.inject(MarketStreamService);
  });

  it('shows REST candles after 6 s, refreshes each minute, and stops when the chart closes', fakeAsync(() => {
    const seen: MarketStreamMessage[] = [];
    const sub = service.watch({ symbol: 'RELIANCE', tf: '5' }).subscribe((m) => seen.push(m));

    tick(5999);
    expect(seen.length).toBe(0);
    tick(1);
    expect(getBootstrap).toHaveBeenCalledWith(jasmine.objectContaining({ symbol: 'RELIANCE', timeframe: '5' }));
    expect(seen[0]).toEqual(jasmine.objectContaining({ op: 'snapshot', source: 'rest', candles: [[1792659000, 1190, 1192, 1188, 1191, 0]] }));

    tick(60_000);
    expect(getBootstrap).toHaveBeenCalledTimes(2);

    sub.unsubscribe();
    tick(120_000);
    expect(getBootstrap).toHaveBeenCalledTimes(2);
  }));
});
