import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { AuthService, User } from '../../core/services/auth.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss'
})
export class DashboardComponent implements OnInit {
  user: User | null = null;
  currentTime = new Date();
  greeting = '';

  stats = [
    { label: 'Market Status', value: 'Open', icon: '🟢', change: null },
    { label: 'NIFTY 50', value: '22,456.80', icon: '📈', change: '+1.25%' },
    { label: 'SENSEX', value: '73,892.45', icon: '📊', change: '+0.98%' },
    { label: 'Announcements Today', value: '47', icon: '📰', change: null }
  ];

  quickActions = [
    { label: 'Compare Stocks', description: 'Analyze price changes between dates', icon: '📊', route: '/stocks' },
    { label: 'F&O Analysis', description: 'View futures and options data', icon: '📈', route: '/fo' },
    { label: 'NSE Announcements', description: 'Latest corporate filings', icon: '📰', route: '/announcements' },
    { label: 'BSE Announcements', description: 'BSE corporate filings', icon: '📋', route: '/announcements' }
  ];

  constructor(private authService: AuthService) { }

  ngOnInit(): void {
    this.authService.currentUser$.subscribe(user => {
      this.user = user;
    });

    this.setGreeting();

    // Update time every minute
    setInterval(() => {
      this.currentTime = new Date();
    }, 60000);
  }

  private setGreeting(): void {
    const hour = this.currentTime.getHours();
    if (hour < 12) {
      this.greeting = 'Good Morning';
    } else if (hour < 17) {
      this.greeting = 'Good Afternoon';
    } else {
      this.greeting = 'Good Evening';
    }
  }
}
