import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface FOData {
  date: string;
  count: number;
  data: any[];
}

export interface FuturesData {
  symbol: string;
  date: string;
  count: number;
  data: any[];
}

export interface OptionsData {
  symbol: string;
  date: string;
  option_type: string | null;
  count: number;
  data: any[];
}

export interface NiftyData {
  date: string;
  futures_count: number;
  options_count: number;
  futures: any[];
  options: any[];
}

@Injectable({
  providedIn: 'root'
})
export class FOService {
  private apiUrl = `${import.meta.env.NG_APP_BACKEND}/api/fo`;

  constructor(private http: HttpClient) { }

  getFOData(date: string, instrumentType?: string): Observable<FOData> {
    let params = new HttpParams();
    if (instrumentType) {
      params = params.set('instrument_type', instrumentType);
    }
    return this.http.get<FOData>(`${this.apiUrl}/data/${date}`, { params });
  }

  getFuturesData(symbol: string, date?: string): Observable<FuturesData> {
    let params = new HttpParams();
    if (date) {
      params = params.set('target_date', date);
    }
    return this.http.get<FuturesData>(`${this.apiUrl}/futures/${symbol}`, { params });
  }

  getOptionsData(symbol: string, date?: string, optionType?: string): Observable<OptionsData> {
    let params = new HttpParams();
    if (date) {
      params = params.set('target_date', date);
    }
    if (optionType) {
      params = params.set('option_type', optionType);
    }
    return this.http.get<OptionsData>(`${this.apiUrl}/options/${symbol}`, { params });
  }

  getNiftyData(date?: string): Observable<NiftyData> {
    let params = new HttpParams();
    if (date) {
      params = params.set('target_date', date);
    }
    return this.http.get<NiftyData>(`${this.apiUrl}/nifty`, { params });
  }
}
