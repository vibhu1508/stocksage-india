import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, combineLatest, defer, map, of, shareReplay } from 'rxjs';

// ngx-env substitutes only variables that are set at build time; an unset one stays as
// import.meta.env.X, which throws in the browser. Read them defensively so a missing
// setting means "off", not a broken page.
function optionalEnv(read: () => string | undefined): string {
  try {
    return read() || '';
  } catch {
    return '';
  }
}

/**
 * Company logos: our own copy in public/logos/ first (listed in its manifest.json), otherwise
 * Brandfetch looked up by ISIN, so each logo belongs to exactly that listed company. Brandfetch
 * images are hotlinked, as their free tier requires; the browser caches them.
 */
@Injectable({ providedIn: 'root' })
export class CompanyLogoService {
  private readonly http = inject(HttpClient);
  private readonly clientId = optionalEnv(() => import.meta.env.NG_APP_BRANDFETCH_CLIENT_ID);
  private readonly missing = new Set<string>();  // ISINs Brandfetch has no logo for, so lists don't retry them
  private readonly brokenLocal = new Set<string>();  // symbols whose local file failed: use Brandfetch instead
  private readonly logoBase = '/logos';

  // One small symbol -> ISIN map per visit (the API serves it with a day of browser caching).
  private readonly isins$ = this.http
    .get<Record<string, string>>(`${import.meta.env.NG_APP_BACKEND}/api/stocks/isin-map`)
    .pipe(catchError(() => of({} as Record<string, string>)), shareReplay(1));

  // Symbol -> file name of the logos kept in public/logos/ (written by scripts/logo-manifest.mjs).
  // Plain fetch: HttpClient's interceptor would attach the login token.
  private readonly local$ = defer(async (): Promise<Record<string, string>> => {
    const r = await fetch(`${this.logoBase}/manifest.json`);
    return r.ok ? r.json() : {};
  }).pipe(catchError(() => of({} as Record<string, string>)), shareReplay(1));

  /** Logo URL for a symbol, or null when there is none to try (the caller shows a letter instead). */
  logoUrl(symbol: string, pixels: number): Observable<string | null> {
    if (!symbol) return of(null);
    const key = symbol.trim().toUpperCase();
    return combineLatest([this.local$, this.isins$]).pipe(
      map(([local, isins]) => {
        if (local[key] && !this.brokenLocal.has(key)) return `${this.logoBase}/${encodeURIComponent(local[key])}`;
        if (!this.clientId) return null;
        const isin = isins[key];
        if (!isin || this.missing.has(isin)) return null;
        // fallback/404 makes a missing logo fail cleanly instead of returning a generic image.
        return `https://cdn.brandfetch.io/isin/${isin}/w/${pixels}/h/${pixels}/fallback/404/type/icon?c=${this.clientId}`;
      }),
    );
  }

  /** Remember a logo that failed to load. True means try again: a broken local file can still
   *  fall back to Brandfetch; a Brandfetch miss means there is no logo to find. */
  markMissing(symbol: string, url: string): boolean {
    if (!url.startsWith('https://cdn.brandfetch.io/')) {
      this.brokenLocal.add(symbol.trim().toUpperCase());
      return true;
    }
    const isin = url.match(/\/isin\/([A-Z0-9]{12})\//)?.[1];
    if (isin) this.missing.add(isin);
    return false;
  }
}
