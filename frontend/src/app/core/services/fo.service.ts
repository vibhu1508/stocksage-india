import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface FOData {
  date: string;
  count: number;
  data: any[];
}

export interface FuturesAnalysisData {
  date: string;
  expiry_date: string;
  available_expiries: string[];
  top_10: any[];
  bottom_10: any[];
  short_covering: any[];
  long_unwinding: any[];
}

export interface FuturesData {
  symbol: string;
  date: string;
  count: number;
  data: any[];
}

/** One strike of the option chain: CE leg, strike, PE leg. */
export interface OptionChainRow {
  StrkPric: number;
  CE_ClsPric: number | null;
  CE_OpnIntrst: number | null;
  CE_ChngInOpnIntrst: number | null;
  CE_pct_oi_change: number | null;
  CE_TtlTradgVol: number | null;
  PE_ClsPric: number | null;
  PE_OpnIntrst: number | null;
  PE_ChngInOpnIntrst: number | null;
  PE_pct_oi_change: number | null;
  PE_TtlTradgVol: number | null;
  PCR: number | null;
}

export interface OptionChainSummary {
  total_ce_oi: number;
  total_pe_oi: number;
  pcr: number | null;
  total_ce_oi_change: number;
  total_pe_oi_change: number;
  max_ce_oi_strike: number | null;
  max_pe_oi_strike: number | null;
  atm_strike: number | null;
  strike_count: number;
}

export interface OptionChainData {
  date: string;
  symbol: string;
  expiry: string | null;
  available_symbols: string[];
  available_expiries: string[];
  underlying_price: number | null;
  chain: OptionChainRow[];
  summary: OptionChainSummary | null;
  count: number;
  data: any[];
}

/** NIFTY tab payload: option chain plus the index futures contracts. */
export interface NiftyData extends OptionChainData {
  futures_count: number;
  options_count: number;
  futures: any[];
  options: any[];
}

export interface FuturesTableRow {
  TckrSymb: string;
  FinInstrmNm: string;
  XpryDt: string;
  UndrlygPric: number | null;
  ClsPric: number | null;
  PrvsClsgPric: number | null;
  pct_price_change: number | null;
  OpnIntrst: number | null;
  ChngInOpnIntrst: number | null;
  pct_oi_change: number | null;
}

export interface FuturesTableData {
  date: string;
  segment: string;
  expiry: string | null;
  symbol: string | null;
  available_expiries: string[];
  available_symbols: string[];
  count: number;
  rows: FuturesTableRow[];
  oi_by_expiry: { XpryDt: string; TckrSymb: string; OpnIntrst: number; ChngInOpnIntrst: number }[];
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

  getFuturesTable(segment: 'index' | 'stock', date?: string, expiry?: string, symbol?: string): Observable<FuturesTableData> {
    let params = new HttpParams().set('segment', segment);
    if (date) params = params.set('target_date', date);
    if (expiry) params = params.set('expiry', expiry);
    if (symbol) params = params.set('symbol', symbol);
    return this.http.get<FuturesTableData>(`${this.apiUrl}/futures-table`, { params });
  }

  getOptionsData(symbol: string, date?: string, expiry?: string, optionType?: string): Observable<OptionChainData> {
    let params = new HttpParams();
    if (date) params = params.set('target_date', date);
    if (expiry) params = params.set('expiry', expiry);
    if (optionType) params = params.set('option_type', optionType);
    return this.http.get<OptionChainData>(`${this.apiUrl}/options/${symbol}`, { params });
  }

  getNiftyData(date?: string, symbol?: string, expiry?: string): Observable<NiftyData> {
    let params = new HttpParams();
    if (date) params = params.set('target_date', date);
    if (symbol) params = params.set('symbol', symbol);
    if (expiry) params = params.set('expiry', expiry);
    return this.http.get<NiftyData>(`${this.apiUrl}/nifty`, { params });
  }

  getFuturesAnalysis(date?: string, expiryMonth?: string): Observable<FuturesAnalysisData> {
    let params = new HttpParams();
    if (date) params = params.set('target_date', date);
    if (expiryMonth) params = params.set('expiry_month', expiryMonth);
    return this.http.get<FuturesAnalysisData>(`${this.apiUrl}/futures-analysis`, { params });
  }
}
