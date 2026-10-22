import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, map, of, shareReplay } from 'rxjs';

// ngx-env substitutes only variables that are set at build time; an unset one stays as
// import.meta.env.X, which throws in the browser. Read it defensively so a missing
// setting means letter badges, not a broken page.
function brandfetchClientId(): string {
  try {
    return import.meta.env.NG_APP_BRANDFETCH_CLIENT_ID || '';
  } catch {
    return '';
  }
}

/**
 * Company logos from Brandfetch, looked up by ISIN so each logo belongs to exactly that listed
 * company. Brandfetch's free tier requires hotlinking (no downloading or caching on our side),
 * so the browser loads each image straight from their CDN and caches it.
 */
@Injectable({ providedIn: 'root' })
export class CompanyLogoService {
  private readonly http = inject(HttpClient);
  private readonly clientId = brandfetchClientId();
  private readonly missing = new Set<string>();  // ISINs Brandfetch has no logo for, so lists don't retry them

  // One small symbol -> ISIN map per visit (the API serves it with a day of browser caching).
  private readonly isins$ = this.http
    .get<Record<string, string>>(`${import.meta.env.NG_APP_BACKEND}/api/stocks/isin-map`)
    .pipe(catchError(() => of({} as Record<string, string>)), shareReplay(1));

  /** Logo URL for a symbol, or null when there is none to try (the caller shows a letter instead). */
  logoUrl(symbol: string, pixels: number): Observable<string | null> {
    if (!this.clientId || !symbol) return of(null);
    const key = symbol.trim().toUpperCase();
    return this.isins$.pipe(
      map((isins) => {
        const isin = isins[key];
        if (!isin || this.missing.has(isin)) return null;
        // fallback/404 makes a missing logo fail cleanly instead of returning a generic image.
        return `https://cdn.brandfetch.io/isin/${isin}/w/${pixels}/h/${pixels}/fallback/404/type/icon?c=${this.clientId}`;
      }),
    );
  }

  markMissing(url: string): void {
    const isin = url.match(/\/isin\/([A-Z0-9]{12})\//)?.[1];
    if (isin) this.missing.add(isin);
  }
}
