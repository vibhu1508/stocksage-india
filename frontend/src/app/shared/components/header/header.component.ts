import { Component, HostListener, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../../core/services/auth.service';
import { LayoutService } from '../../../core/services/layout.service';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './header.component.html',
  styleUrl: './header.component.scss'
})
export class HeaderComponent implements OnInit {
  currentDate = new Date();

  isVisible = true;
  isVideoPlaying = false;
  private lastScrollY = 0;

  constructor(
    public authService: AuthService,
    private layoutService: LayoutService
  ) { }

  ngOnInit() {
    this.layoutService.videoPlaying$.subscribe(playing => {
      this.isVideoPlaying = playing;
    });
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
