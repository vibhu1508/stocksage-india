import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.scss'
})
export class SidebarComponent {
  menuItems = [
    { path: '/dashboard', icon: 'dashboard', label: 'Dashboard' },
    { path: '/stocks', icon: 'trending_up', label: 'Stock Comparison' },
    { path: '/fo', icon: 'show_chart', label: 'F&O Analysis' },
    { path: '/announcements', icon: 'campaign', label: 'Announcements' }
  ];

  constructor(public authService: AuthService) { }
}
