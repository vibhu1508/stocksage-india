import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-callback',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="callback-page">
      <div class="callback-shell">
        @if (error) {
          <div class="error-state">
            <h2>Authentication failed</h2>
            <p>{{ error }}</p>
            <button class="btn" (click)="goToLogin()">Back to login</button>
          </div>
        } @else {
          <div class="loading-state">
            <div class="loader-wrap" aria-hidden="true">
              <div class="spinner"></div>
              <div class="logo-mark">S</div>
            </div>
            <h2>Authenticating...</h2>
            <p>Redirecting to StockSage India</p>
          </div>
        }
      </div>
    </div>
  `,
  styles: [`
    @use '../../../../styles/variables' as *;
    @use '../../../../styles/mixins' as *;

    :host {
      display: block;
      width: 100%;
    }

    .callback-page {
      min-height: calc(100vh - 4rem);
      width: 100%;
      display: grid;
      place-items: center;
      padding: $spacing-xl;
      background: var(--background);
    }

    .callback-shell {
      width: min(100%, 520px);
      padding: $spacing-xxl;
      border-radius: 20px;
      border: 1px solid var(--border);
      background: var(--card);
      box-shadow: 0 20px 50px rgba(15, 23, 42, 0.08);
      text-align: center;
    }

    .loading-state, .error-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: $spacing-sm;
    }

    .loader-wrap {
      position: relative;
      width: 84px;
      height: 84px;
      margin-bottom: $spacing-md;
    }

    .logo-mark {
      position: absolute;
      inset: 19px;
      display: grid;
      place-items: center;
      border-radius: 14px;
      font-family: 'Outfit', sans-serif;
      font-weight: 700;
      font-size: 1.35rem;
      color: #ffffff;
      background: linear-gradient(135deg, #4f8efb, #5f79ff);
      box-shadow: 0 10px 24px rgba(79, 142, 251, 0.32);
    }

    .spinner {
      width: 84px;
      height: 84px;
      border: 3px solid rgba(107, 129, 199, 0.2);
      border-top-color: #4f8efb;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    h2 {
      margin: 0;
      color: var(--foreground);
      font-size: 2rem;
      font-family: 'Outfit', sans-serif;
      letter-spacing: 0.01em;
    }

    p {
      color: var(--muted-foreground);
      margin: 0;
      max-width: 34ch;
      line-height: 1.45;
      font-size: 1rem;
    }

    .btn {
      @include button-primary;
      margin-top: $spacing-md;
      min-width: 170px;
    }

    @media (max-width: 640px) {
      .callback-page {
        padding: $spacing-md;
      }

      .callback-shell {
        padding: $spacing-xl $spacing-lg;
      }

      h2 {
        font-size: 1.6rem;
      }
    }
  `]
})
export class CallbackComponent implements OnInit {
  error: string | null = null;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private authService: AuthService
  ) { }

  ngOnInit(): void {
    const token = this.route.snapshot.queryParamMap.get('token');
    const error = this.route.snapshot.queryParamMap.get('error');

    if (error) {
      this.error = error;
    } else if (token) {
      this.authService.handleCallback(token);
    } else {
      this.error = 'No authentication token received';
    }
  }

  goToLogin(): void {
    this.router.navigate(['/login']);
  }
}
