import { Component, Output, EventEmitter } from '@angular/core';
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
  collapsed = false;
  mobileOpen = false;

  @Output() collapsedChange = new EventEmitter<boolean>();

  menuItems = [
    { path: '/dashboard', icon: 'dashboard', label: 'Dashboard' },
    { path: '/chart', icon: 'candlestick_chart', label: 'Charts' },
    { path: '/stocks', icon: 'trending_up', label: 'Stock Comparison' },
    { path: '/fo', icon: 'show_chart', label: 'F&O Analysis' },
    { path: '/announcements', icon: 'campaign', label: 'Announcements' },
    { path: '/learn', icon: 'school', label: 'Learn' }
  ];

  constructor(public authService: AuthService) { }

  toggleCollapse(): void {
    this.collapsed = !this.collapsed;
    this.collapsedChange.emit(this.collapsed);
  }

  toggleMobile(): void {
    this.mobileOpen = !this.mobileOpen;
  }

  closeMobile(): void {
    this.mobileOpen = false;
  }
}
