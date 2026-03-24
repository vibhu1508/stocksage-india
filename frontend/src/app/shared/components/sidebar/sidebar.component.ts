import { Component, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { LucideAngularModule } from 'lucide-angular';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [
    CommonModule, 
    RouterLink, 
    RouterLinkActive,
    LucideAngularModule
  ],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.scss'
})
export class SidebarComponent {
  collapsed = false;
  mobileOpen = false;

  @Output() collapsedChange = new EventEmitter<boolean>();

  menuItems = [
    { path: '/dashboard', icon: 'layout-dashboard', label: 'Dashboard' },
    { path: '/stocks', icon: 'arrow-up-right', label: 'Stock Comparison' },
    { path: '/fo', icon: 'line-chart', label: 'F&O Analysis' },
    { path: '/strategy-builder', icon: 'pencil-ruler', label: 'Strategy Builder' },
    { path: '/announcements', icon: 'megaphone', label: 'Announcements' },
    { path: '/learn', icon: 'graduation-cap', label: 'Learn' }
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
