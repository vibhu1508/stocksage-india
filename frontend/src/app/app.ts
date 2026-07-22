import { Component } from '@angular/core';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { SidebarComponent } from './shared/components/sidebar/sidebar.component';
import { HeaderComponent } from './shared/components/header/header.component';
import { AiAssistantComponent } from './shared/components/ai-assistant/ai-assistant.component';
import { AuthService } from './core/services/auth.service';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, SidebarComponent, HeaderComponent, AiAssistantComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App {
  sidebarCollapsed = false;

  /** Routes that render full-bleed, without the dashboard sidebar/header shell. */
  private readonly chromelessRoutes = ['/', '/login'];
  private currentUrl = '/';

  constructor(public authService: AuthService, private router: Router) {
    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe((e) => {
        this.currentUrl = e.urlAfterRedirects.split('?')[0].split('#')[0];
      });
  }

  /** The app shell (sidebar + header) only wraps real app routes for a signed-in user. */
  get showShell(): boolean {
    return this.authService.isAuthenticated() && !this.chromelessRoutes.includes(this.currentUrl);
  }
}
