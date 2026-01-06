import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AnnouncementService, NSEAnnouncement, BSEAnnouncement } from '../../core/services/announcement.service';

interface ScripCode {
  'Scrip Code': string;
  'Company Name': string;
}

@Component({
  selector: 'app-announcements',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './announcements.component.html',
  styleUrl: './announcements.component.scss'
})
export class AnnouncementsComponent implements OnInit {
  activeTab: 'nse' | 'bse' = 'nse';

  // NSE filters
  nseSymbol = 'RELIANCE';
  nseFromDate = '';
  nseToDate = '';
  nseLimit = 100;

  // BSE filters
  bseFromDate = '';
  bseToDate = '';
  bseScripCode = '';  // Added for company filter
  bseScripCodes: ScripCode[] = [];  // List of available companies

  loading = false;
  error: string | null = null;

  nseAnnouncements: NSEAnnouncement[] = [];
  bseAnnouncements: BSEAnnouncement[] = [];

  // Popular symbols for quick selection
  popularSymbols = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'AXISBANK', 'SBIN', 'BHARTIARTL'];

  constructor(private announcementService: AnnouncementService) { }

  ngOnInit(): void {
    // Set default dates
    const today = new Date();
    const weekAgo = new Date(today);
    weekAgo.setDate(weekAgo.getDate() - 7);

    // Set dates for both NSE and BSE
    this.nseToDate = this.formatDate(today);
    this.nseFromDate = this.formatDate(weekAgo);
    this.bseToDate = this.formatDate(today);
    this.bseFromDate = this.formatDate(weekAgo);

    this.loadNSEAnnouncements();
    this.loadBSEScripCodes();  // Load company list for dropdown
  }

  private formatDate(date: Date): string {
    return date.toISOString().split('T')[0];
  }

  loadBSEScripCodes(): void {
    this.announcementService.getBSEScripCodes().subscribe({
      next: (response) => {
        this.bseScripCodes = response.scrip_codes as ScripCode[];
      },
      error: (err) => {
        console.error('Failed to load BSE scrip codes:', err);
      }
    });
  }

  onTabChange(tab: 'nse' | 'bse'): void {
    this.activeTab = tab;
    this.error = null;

    if (tab === 'nse' && this.nseAnnouncements.length === 0) {
      this.loadNSEAnnouncements();
    } else if (tab === 'bse' && this.bseAnnouncements.length === 0) {
      this.loadBSEAnnouncements();
    }
  }

  loadNSEAnnouncements(): void {
    this.loading = true;
    this.error = null;

    this.announcementService.getNSEAnnouncements(
      this.nseSymbol,
      this.nseFromDate || undefined,
      this.nseToDate || undefined,
      this.nseLimit
    ).subscribe({
      next: (response) => {
        this.nseAnnouncements = response.announcements;
        this.loading = false;
      },
      error: (err) => {
        this.error = err.error?.detail || 'Failed to load NSE announcements';
        this.loading = false;
      }
    });
  }

  loadBSEAnnouncements(): void {
    this.loading = true;
    this.error = null;

    // Pass scrip code if selected (for company filtering)
    const scripCode = this.bseScripCode || undefined;

    this.announcementService.getBSEAnnouncements(scripCode, this.bseFromDate, this.bseToDate).subscribe({
      next: (response) => {
        this.bseAnnouncements = response.announcements;
        this.loading = false;
      },
      error: (err) => {
        this.error = err.error?.detail || 'Failed to load BSE announcements';
        this.loading = false;
      }
    });
  }

  selectSymbol(symbol: string): void {
    this.nseSymbol = symbol;
    this.loadNSEAnnouncements();
  }

  openAttachment(url: string): void {
    if (url) {
      window.open(url, '_blank');
    }
  }
}

