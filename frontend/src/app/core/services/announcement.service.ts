import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface NSEAnnouncement {
  symbol: string;
  company_name: string;
  subject: string;
  broadcast_date: string;
  attachment_link: string;
  category: string;
}

export interface BSEAnnouncement {
  scrip_code: string;
  company_name: string;
  subject: string;
  news_date: string;
  category: string;
  attachment_url: string | null;
  news_id: string;
}

export interface NSEAnnouncementsResponse {
  symbol: string;
  count: number;
  announcements: NSEAnnouncement[];
  message?: string;
}

export interface BSEAnnouncementsResponse {
  scrip_code: string | null;
  from_date: string | null;
  to_date: string | null;
  announcements: BSEAnnouncement[];
  total_pages: number;
  current_page: number;
}

@Injectable({
  providedIn: 'root'
})
export class AnnouncementService {
  private apiUrl = `${import.meta.env.NG_APP_BACKEND}/api/announcements`;

  constructor(private http: HttpClient) { }

  getNSEAnnouncements(symbol: string, fromDate?: string, toDate?: string, limit: number = 100): Observable<NSEAnnouncementsResponse> {
    let params = new HttpParams().set('limit', limit.toString());

    if (fromDate) {
      params = params.set('from_date', fromDate);
    }
    if (toDate) {
      params = params.set('to_date', toDate);
    }

    return this.http.get<NSEAnnouncementsResponse>(`${this.apiUrl}/nse/${symbol}`, { params });
  }

  getBSEAnnouncements(
    scripCode?: string,
    fromDate?: string,
    toDate?: string,
    page: number = 1
  ): Observable<BSEAnnouncementsResponse> {
    let params = new HttpParams().set('page', page.toString());

    if (scripCode) {
      params = params.set('scrip_code', scripCode);
    }
    if (fromDate) {
      params = params.set('from_date', fromDate);
    }
    if (toDate) {
      params = params.set('to_date', toDate);
    }

    return this.http.get<BSEAnnouncementsResponse>(`${this.apiUrl}/bse`, { params });
  }

  getBSEScripCodes(): Observable<{ count: number; scrip_codes: any[] }> {
    return this.http.get<{ count: number; scrip_codes: any[] }>(`${this.apiUrl}/bse/scrip-codes`);
  }
}
