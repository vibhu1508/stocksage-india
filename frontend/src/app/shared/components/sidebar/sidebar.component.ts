import { Component, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { AiAssistantService } from '../../../core/services/ai-assistant.service';
import { SageIconComponent } from '../sage-icon/sage-icon.component';
import { LucideAngularModule } from 'lucide-angular';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    RouterLinkActive,
    LucideAngularModule,
    SageIconComponent
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
    { path: '/portfolio', icon: 'briefcase', label: 'Portfolio' },
    { path: '/stocks', icon: 'bar-chart-2', label: 'Watchlist' },
    { path: '/after-market-analysis', icon: 'line-chart', label: 'After Market Analysis' },
    { path: '/strategy-builder', icon: 'pencil-ruler', label: 'Strategy Builder' },
    { path: '/announcements', icon: 'megaphone', label: 'Announcements' },
    { path: '/learn', icon: 'graduation-cap', label: 'Learn' }
  ];

  constructor(
    public authService: AuthService,
    public aiAssistant: AiAssistantService,
  ) { }

  openAssistant(): void {
    this.aiAssistant.open();
    this.closeMobile();
  }

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
