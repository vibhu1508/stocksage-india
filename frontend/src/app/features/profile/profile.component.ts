import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService, OnboardingPayload, User } from '../../core/services/auth.service';
import { LucideAngularModule } from 'lucide-angular';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule],
  templateUrl: './profile.component.html',
  styleUrl: './profile.component.scss'
})
export class ProfileComponent implements OnInit {
  loading = false;
  saving = false;
  error = '';
  success = '';

  user: User | null = null;

  form: OnboardingPayload = {
    phone: '',
    address: '',
    occupation: '',
    trading_experience: 'Beginner'
  };

  constructor(private authService: AuthService) {}

  ngOnInit(): void {
    this.loadProfile();
  }

  loadProfile(): void {
    this.loading = true;
    this.error = '';

    this.authService.fetchCurrentUser().subscribe({
      next: (user) => {
        this.user = user;
        this.form = {
          phone: user.phone || '',
          address: user.address || '',
          occupation: user.occupation || '',
          trading_experience: user.trading_experience || 'Beginner'
        };
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.detail || 'Unable to load profile details.';
      }
    });
  }

  saveProfile(): void {
    this.saving = true;
    this.error = '';
    this.success = '';

    this.authService.saveOnboarding(this.form).subscribe({
      next: () => {
        this.saving = false;
        this.success = 'Profile updated successfully.';
      },
      error: (err) => {
        this.saving = false;
        this.error = err?.error?.detail || 'Unable to update profile. Please try again.';
      }
    });
  }
}
