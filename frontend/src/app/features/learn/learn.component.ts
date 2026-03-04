import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { Subject, Subscription } from 'rxjs';
import { debounceTime, distinctUntilChanged } from 'rxjs/operators';
import { MarketService, LearnVideo } from '../../core/services/market.service';
import { LayoutService } from '../../core/services/layout.service';

@Component({
  selector: 'app-learn',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './learn.component.html',
  styleUrl: './learn.component.scss'
})
export class LearnComponent implements OnInit, OnDestroy {
  videos: LearnVideo[] = [];
  loading = true;
  searchQuery = '';
  nextPageToken = '';
  loadingMore = false;

  // Video player
  selectedVideo: LearnVideo | null = null;
  playerUrl: SafeResourceUrl | null = null;

  // Dynamic search
  private searchSubject = new Subject<string>();
  private searchSub?: Subscription;

  constructor(
    private marketService: MarketService,
    private sanitizer: DomSanitizer,
    private layoutService: LayoutService
  ) { }

  ngOnInit(): void {
    this.fetchVideos();

    // Dynamic search: debounce 400ms, trigger after 2+ chars or empty (reset)
    this.searchSub = this.searchSubject.pipe(
      debounceTime(400),
      distinctUntilChanged()
    ).subscribe(query => {
      if (query.length === 0) {
        this.fetchVideos();
      } else if (query.length >= 2) {
        this.doSearch(query);
      }
    });
  }

  ngOnDestroy(): void {
    this.searchSub?.unsubscribe();
    this.layoutService.setVideoPlaying(false);
  }

  onSearchInput(value: string): void {
    this.searchSubject.next(value);
  }

  fetchVideos(pageToken: string = ''): void {
    if (!pageToken) {
      this.loading = true;
    }
    this.marketService.getLearnVideos(pageToken).subscribe(data => {
      if (pageToken) {
        this.videos = [...this.videos, ...data.videos];
      } else {
        this.videos = data.videos;
      }
      this.nextPageToken = data.nextPageToken;
      this.loading = false;
      this.loadingMore = false;
    });
  }

  private doSearch(query: string): void {
    this.loading = true;
    this.marketService.searchLearnVideos(query).subscribe(data => {
      this.videos = data.videos;
      this.nextPageToken = data.nextPageToken;
      this.loading = false;
    });
  }

  loadMore(): void {
    if (!this.nextPageToken || this.loadingMore) return;
    this.loadingMore = true;
    if (this.searchQuery.trim() && this.searchQuery.length >= 2) {
      this.marketService.searchLearnVideos(this.searchQuery, this.nextPageToken).subscribe(data => {
        this.videos = [...this.videos, ...data.videos];
        this.nextPageToken = data.nextPageToken;
        this.loadingMore = false;
      });
    } else {
      this.fetchVideos(this.nextPageToken);
    }
  }

  playVideo(video: LearnVideo): void {
    this.layoutService.setVideoPlaying(true);
    this.selectedVideo = video;
    this.playerUrl = this.sanitizer.bypassSecurityTrustResourceUrl(
      `https://www.youtube.com/embed/${video.videoId}?autoplay=1&rel=0`
    );
  }

  closePlayer(): void {
    this.layoutService.setVideoPlaying(false);
    this.selectedVideo = null;
    this.playerUrl = null;
  }

  formatViews(views: number): string {
    if (views >= 1000000) return (views / 1000000).toFixed(1) + 'M';
    if (views >= 1000) return (views / 1000).toFixed(1) + 'K';
    return views.toString();
  }

  formatDuration(iso: string): string {
    const match = /PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/.exec(iso);
    if (!match) return '';
    const h = parseInt(match[1] || '0');
    const m = parseInt(match[2] || '0');
    const s = parseInt(match[3] || '0');
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  timeAgo(dateStr: string): string {
    try {
      const date = new Date(dateStr);
      const diff = Date.now() - date.getTime();
      const days = Math.floor(diff / 86400000);
      if (days > 365) return Math.floor(days / 365) + 'y ago';
      if (days > 30) return Math.floor(days / 30) + 'mo ago';
      if (days > 0) return days + 'd ago';
      const hours = Math.floor(diff / 3600000);
      if (hours > 0) return hours + 'h ago';
      return Math.floor(diff / 60000) + 'm ago';
    } catch {
      return '';
    }
  }

  clearSearch(): void {
    this.searchQuery = '';
    this.fetchVideos();
  }
}
