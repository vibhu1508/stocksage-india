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
          // If token is invalid/expired (401), clear everything
          if (err.status === 401) {
            this.clearSession();
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
    return localStorage.getItem('access_token');
  }

  setToken(token: string): void {
    localStorage.setItem('access_token', token);
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
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
      next: () => this.router.navigate(['/dashboard']),
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

  logout(): void {
    const token = this.getToken();
    if (token) {
      // Best effort logout on backend
      this.http.post(`${this.apiUrl}/logout`, {}).subscribe({
        next: () => this.finalizeLogout(),
        error: () => this.finalizeLogout()
      });
    } else {
      this.finalizeLogout();
    }
  }

  private finalizeLogout(): void {
    localStorage.removeItem('access_token');
    this.currentUserSubject.next(null);
    this.router.navigate(['/login']);
  }
}
