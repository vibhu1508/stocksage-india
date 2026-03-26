import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { Router } from '@angular/router';

export interface User {
  id: number;
  email: string;
  name: string;
  picture: string;
  is_admin: boolean;
  phone?: string | null;
  address?: string | null;
  occupation?: string | null;
  trading_experience?: string | null;
  onboarding_completed?: boolean;
  onboarding_skipped?: boolean;
}

export interface OnboardingPayload {
  phone: string;
  address: string;
  occupation: string;
  trading_experience: string;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = `${import.meta.env.NG_APP_BACKEND}/api/auth`;
  private currentUserSubject = new BehaviorSubject<User | null>(null);
  public currentUser$ = this.currentUserSubject.asObservable();

  constructor(
    private http: HttpClient,
    private router: Router
  ) {
    // Check for existing token on init
    this.loadUserFromToken();
  }

  private loadUserFromToken(): void {
    const token = this.getToken();
    if (token) {
      this.fetchCurrentUser().subscribe({
        next: (user) => {
          this.currentUserSubject.next(user);
        },
        error: (err) => {
          // If token is invalid/expired (401), clear session and redirect to login.
          if (err.status === 401) {
            this.handleUnauthorizedSession(this.router.url || '/dashboard');
          }
        }
      });
    }
  }

  private clearSession(): void {
    localStorage.removeItem('access_token');
    this.currentUserSubject.next(null);
  }

  getToken(): string | null {
    const token = localStorage.getItem('access_token');
    if (!token) {
      return null;
    }

    if (this.isTokenExpired(token)) {
      this.clearSession();
      return null;
    }

    return token;
  }

  setToken(token: string): void {
    localStorage.setItem('access_token', token);
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }

  handleUnauthorizedSession(returnUrl?: string): void {
    const targetUrl = returnUrl || this.router.url || '/dashboard';
    const isAuthRoute = targetUrl.startsWith('/login') || targetUrl.startsWith('/auth/callback');
    this.finalizeLogout(isAuthRoute ? null : targetUrl);
  }

  get currentUser(): User | null {
    return this.currentUserSubject.value;
  }

  loginWithGoogle(): void {
    // Redirect to backend Google OAuth endpoint
    window.location.href = `${this.apiUrl}/google/login`;
  }

  handleCallback(token: string): void {
    this.setToken(token);
    this.fetchCurrentUser().subscribe({
      next: (user) => {
        if (!user.onboarding_completed && !user.onboarding_skipped) {
          this.router.navigate(['/onboarding']);
          return;
        }
        this.router.navigate(['/dashboard']);
      },
      error: () => {
        this.logout();
        this.router.navigate(['/login']);
      }
    });
  }

  fetchCurrentUser(): Observable<User> {
    return this.http.get<User>(`${this.apiUrl}/me`).pipe(
      tap(user => this.currentUserSubject.next(user))
    );
  }

  saveOnboarding(payload: OnboardingPayload): Observable<{ message: string; user: User }> {
    return this.http.put<{ message: string; user: User }>(`${this.apiUrl}/onboarding`, payload).pipe(
      tap((response) => this.currentUserSubject.next(response.user))
    );
  }

  skipOnboarding(): Observable<{ message: string; onboarding_skipped: boolean }> {
    return this.http.post<{ message: string; onboarding_skipped: boolean }>(`${this.apiUrl}/onboarding/skip`, {}).pipe(
      tap(() => {
        const current = this.currentUserSubject.value;
        if (!current) return;
        this.currentUserSubject.next({
          ...current,
          onboarding_skipped: true,
        });
      })
    );
  }

  logout(): void {
    const token = this.getToken();
    // Always clear local auth state immediately so logout feels instant.
    this.finalizeLogout();

    if (!token) {
      return;
    }

    // Best effort server-side session invalidation in the background.
    this.http.post(
      `${this.apiUrl}/logout`,
      {},
      {
        headers: new HttpHeaders({
          Authorization: `Bearer ${token}`
        })
      }
    ).subscribe({
      next: () => {},
      error: () => {}
    });
  }

  private finalizeLogout(returnUrl: string | null = null): void {
    localStorage.removeItem('access_token');
    this.currentUserSubject.next(null);

    if (returnUrl) {
      this.router.navigate(['/login'], { queryParams: { returnUrl } });
      return;
    }

    this.router.navigate(['/login']);
  }

  private isTokenExpired(token: string): boolean {
    const payload = this.decodeJwtPayload(token);
    if (!payload || typeof payload.exp !== 'number') {
      return true;
    }

    const nowInSeconds = Math.floor(Date.now() / 1000);
    return payload.exp <= nowInSeconds;
  }

  private decodeJwtPayload(token: string): any | null {
    try {
      const tokenParts = token.split('.');
      if (tokenParts.length < 2) {
        return null;
      }

      const base64Payload = tokenParts[1].replace(/-/g, '+').replace(/_/g, '/');
      const paddingLength = (4 - (base64Payload.length % 4)) % 4;
      const paddedBase64 = base64Payload + '='.repeat(paddingLength);
      const decodedPayload = atob(paddedBase64);
      return JSON.parse(decodedPayload);
    } catch {
      return null;
    }
  }
}
