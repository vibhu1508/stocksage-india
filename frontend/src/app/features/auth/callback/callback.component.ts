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
      <div class="callback-card">
        @if (error) {
          <div class="error-state">
            <span class="error-icon">❌</span>
            <h2>Authentication Failed</h2>
            <p>{{ error }}</p>
            <button class="btn" (click)="goToLogin()">Try Again</button>
          </div>
        } @else {
          <div class="loading-state">
            <div class="spinner"></div>
            <h2>Authenticating...</h2>
            <p>Please wait while we sign you in</p>
          </div>
        }
      </div>
    </div>
  `,
  styles: [`
    @use '../../../../styles/variables' as *;
    @use '../../../../styles/mixins' as *;

    .callback-page {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: $primary-dark;
    }

    .callback-card {
      @include glass-card;
      padding: $spacing-xxl;
      text-align: center;
      min-width: 320px;
    }

    .loading-state, .error-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: $spacing-md;
    }

    .spinner {
      width: 48px;
      height: 48px;
      border: 3px solid $glass-border;
      border-top-color: $accent-primary;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .error-icon {
      font-size: 48px;
    }

    h2 {
      margin: 0;
      font-size: 1.25rem;
    }

    p {
      color: $text-secondary;
      margin: 0;
    }

    .btn {
      @include button-primary;
      margin-top: $spacing-md;
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
