import { Component, HostListener, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../../core/services/auth.service';
import { LayoutService } from '../../../core/services/layout.service';
import { ThemeService } from '../../../core/services/theme.service';
import { ClockService } from '../../../core/services/clock.service';
import { LucideAngularModule } from 'lucide-angular';
import { Observable } from 'rxjs';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule, LucideAngularModule],
  templateUrl: './header.component.html',
  styleUrl: './header.component.scss'
})
export class HeaderComponent implements OnInit {
  timeParts$: Observable<any>;
  isVisible = true;
  isVideoPlaying = false;
  private lastScrollY = 0;

  constructor(
    public authService: AuthService,
    private layoutService: LayoutService,
    public themeService: ThemeService,
    public clockService: ClockService
  ) { 
    this.timeParts$ = this.clockService.timeParts$;
  }

  ngOnInit() {
    this.layoutService.videoPlaying$.subscribe(playing => {
      this.isVideoPlaying = playing;
    });

    // The theme initialization logic is now handled within ThemeService
    // const savedTheme = localStorage.getItem('theme');
    // if (savedTheme === 'light') {
    //   this.isDarkTheme = false;
    //   document.documentElement.classList.remove('dark');
    // } else {
    //   this.isDarkTheme = true;
    //   document.documentElement.classList.add('dark');
    // }
  }

  toggleTheme(): void {
    this.themeService.toggleTheme();
  }

  get showHeader(): boolean {
    return this.isVisible && !this.isVideoPlaying;
  }

  @HostListener('window:scroll', [])
  onWindowScroll() {
    const currentScrollY = window.pageYOffset || document.documentElement.scrollTop;

    // Threshold of 60px before triggering header hide logic
    if (currentScrollY > 60) {
      if (currentScrollY > this.lastScrollY) {
        // Scrolling down
        this.isVisible = false;
      } else {
        // Scrolling up
        this.isVisible = true;
      }
    } else {
      // At the top
      this.isVisible = true;
    }

    this.lastScrollY = currentScrollY;
  }

  logout(): void {
    this.authService.logout();
  }
}
