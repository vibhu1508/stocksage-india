import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService, OnboardingPayload } from '../../core/services/auth.service';
import { LucideAngularModule } from 'lucide-angular';

@Component({
  selector: 'app-onboarding',
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule],
  templateUrl: './onboarding.component.html',
  styleUrl: './onboarding.component.scss'
})
export class OnboardingComponent {
  loading = false;
  error = '';

  form: OnboardingPayload = {
    phone: '',
    address: '',
    occupation: '',
    trading_experience: 'Beginner'
  };

  constructor(
    private authService: AuthService,
    private router: Router
  ) {}

  save(): void {
    this.error = '';
    this.loading = true;
    this.authService.saveOnboarding(this.form).subscribe({
      next: () => {
        this.loading = false;
        this.router.navigate(['/portfolio']);
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.detail || 'Unable to save onboarding details. Please try again.';
      }
    });
  }

  skip(): void {
    this.error = '';
    this.loading = true;
    this.authService.skipOnboarding().subscribe({
      next: () => {
        this.loading = false;
        this.router.navigate(['/dashboard']);
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.detail || 'Unable to skip right now. Please try again.';
      }
    });
  }
}
