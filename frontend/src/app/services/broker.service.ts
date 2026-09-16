import { Inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, of, throwError } from 'rxjs';
import { catchError, tap } from 'rxjs/operators';
import { isPlatformBrowser } from '@angular/common';

/**
 * Link state plus the server-side gates.
 *
 * The gates are included so the UI can explain *why* live trading is
 * unavailable rather than letting the user fill in a form that is going to be
 * rejected server-side.
 */
export interface BrokerStatus {
  linked: boolean;
  provider?: string;
  mode: 'paper' | 'live' | null;
  is_enabled: boolean;
  broker_account_id?: string | null;
  linked_at?: string | null;
  live_confirmed?: boolean;
  last_sync_at?: string | null;
  encryption_configured: boolean;
  server_allows_live: boolean;
  server_allows_live_bot: boolean;
}

export interface BrokerAccount {
  account_number: string | null;
  status: string;
  cash: number;
  buying_power: number;
  equity: number;
  portfolio_value: number;
  currency: string;
  trading_blocked: boolean;
  account_blocked: boolean;
  pattern_day_trader: boolean;
  daytrade_count: number;
}

export interface BrokerPosition {
  symbol: string;
  qty: number;
  avg_entry_price: number;
  market_value: number;
  unrealized_pl: number;
  current_price: number;
}

export interface MarketClock {
  is_open: boolean;
  next_open: string | null;
  next_close: string | null;
}

export interface SyncResult {
  synced_at: string;
  cash: number;
  equity: number;
  buying_power: number;
  positions: number;
  trading_blocked: boolean;
}

export interface ReconcileResult {
  checked: number;
  updated: number;
}

@Injectable({
  providedIn: 'root',
})
export class BrokerService {
  private readonly apiUrl = '/api/broker';

  /**
   * Shared link state. Other components (the trading page, the bot controls)
   * read this to show whether orders are going to a real broker or being
   * simulated, so that indicator can never disagree with this page.
   */
  private readonly statusSubject = new BehaviorSubject<BrokerStatus | null>(null);
  public readonly status$: Observable<BrokerStatus | null> = this.statusSubject.asObservable();

  /** Signal mirror of the same state, for components using the signals API. */
  public readonly status = signal<BrokerStatus | null>(null);

  constructor(
    private http: HttpClient,
    @Inject(PLATFORM_ID) private platformId: Object,
  ) {
    if (isPlatformBrowser(this.platformId)) {
      this.refreshStatus().subscribe();
    }
  }

  // --- Status ---------------------------------------------------------------

  refreshStatus(): Observable<BrokerStatus | null> {
    if (!isPlatformBrowser(this.platformId)) {
      return of(null);
    }

    return this.http
      .get<BrokerStatus>(`${this.apiUrl}/status`, { withCredentials: true })
      .pipe(
        tap((status) => this.publish(status)),
        catchError((err) => {
          console.error('Failed to fetch broker status:', err);
          return of(null);
        }),
      );
  }

  // --- Linking --------------------------------------------------------------

  /** Link an Alpaca PAPER account. Keys are verified server-side before storage. */
  linkPaper(apiKey: string, secretKey: string): Observable<BrokerStatus> {
    return this.http
      .post<BrokerStatus>(
        `${this.apiUrl}/link`,
        { api_key: apiKey, secret_key: secretKey },
        { withCredentials: true },
      )
      .pipe(
        tap(() => this.refreshStatus().subscribe()),
        catchError((err) => throwError(() => this.describe(err))),
      );
  }

  /**
   * Promote to LIVE trading.
   *
   * Requires a separate live key pair — Alpaca issues different credentials for
   * paper and live, so this is not a flag flip.
   */
  linkLive(apiKey: string, secretKey: string): Observable<BrokerStatus> {
    return this.http
      .post<BrokerStatus>(
        `${this.apiUrl}/link/live`,
        { api_key: apiKey, secret_key: secretKey, acknowledge_real_money: true },
        { withCredentials: true },
      )
      .pipe(
        tap(() => this.refreshStatus().subscribe()),
        catchError((err) => throwError(() => this.describe(err))),
      );
  }

  /** Pause or resume broker routing without discarding stored keys. */
  setEnabled(enabled: boolean): Observable<BrokerStatus> {
    return this.http
      .post<BrokerStatus>(`${this.apiUrl}/enabled`, { enabled }, { withCredentials: true })
      .pipe(
        tap(() => this.refreshStatus().subscribe()),
        catchError((err) => throwError(() => this.describe(err))),
      );
  }

  /** Delete stored credentials. Trade history is retained. */
  unlink(): Observable<unknown> {
    return this.http.delete(`${this.apiUrl}/unlink`, { withCredentials: true }).pipe(
      tap(() => this.refreshStatus().subscribe()),
      catchError((err) => throwError(() => this.describe(err))),
    );
  }

  // --- Reads ----------------------------------------------------------------

  getAccount(): Observable<BrokerAccount> {
    return this.http
      .get<BrokerAccount>(`${this.apiUrl}/account`, { withCredentials: true })
      .pipe(catchError((err) => throwError(() => this.describe(err))));
  }

  getPositions(): Observable<BrokerPosition[]> {
    return this.http
      .get<BrokerPosition[]>(`${this.apiUrl}/positions`, { withCredentials: true })
      .pipe(catchError((err) => throwError(() => this.describe(err))));
  }

  getClock(): Observable<MarketClock> {
    return this.http
      .get<MarketClock>(`${this.apiUrl}/clock`, { withCredentials: true })
      .pipe(catchError((err) => throwError(() => this.describe(err))));
  }

  // --- Actions --------------------------------------------------------------

  /** Force a refresh of local balance and holdings from Alpaca. */
  sync(): Observable<SyncResult> {
    return this.http
      .post<SyncResult>(`${this.apiUrl}/sync`, {}, { withCredentials: true })
      .pipe(
        tap(() => this.refreshStatus().subscribe()),
        catchError((err) => throwError(() => this.describe(err))),
      );
  }

  /** Update any still-working orders with their current broker status. */
  reconcile(): Observable<ReconcileResult> {
    return this.http
      .post<ReconcileResult>(`${this.apiUrl}/reconcile`, {}, { withCredentials: true })
      .pipe(catchError((err) => throwError(() => this.describe(err))));
  }

  // --- Helpers --------------------------------------------------------------

  public get currentStatus(): BrokerStatus | null {
    return this.statusSubject.value;
  }

  /** True when orders are being routed to a real broker rather than simulated. */
  public get isRouting(): boolean {
    const s = this.statusSubject.value;
    return !!s && s.linked && s.is_enabled;
  }

  private publish(status: BrokerStatus): void {
    this.statusSubject.next(status);
    this.status.set(status);
  }

  /**
   * FastAPI puts the useful message in `detail`. Surfacing that verbatim matters
   * here: the backend's errors explain which live-trading gate is closed, and
   * replacing them with a generic "something went wrong" would leave the user
   * with no way to work out what to change.
   */
  private describe(err: any): Error {
    const detail = err?.error?.detail;
    if (typeof detail === 'string') {
      return new Error(detail);
    }
    if (err?.status === 0) {
      return new Error('Could not reach the server. Check that the backend is running.');
    }
    return new Error(err?.message || 'Unexpected error contacting the broker.');
  }
}
