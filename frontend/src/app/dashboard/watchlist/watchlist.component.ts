import { ChangeDetectionStrategy, Component, signal, OnInit, OnDestroy, inject, PLATFORM_ID } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { AuthService } from '../../auth.service';
import { forkJoin, of, Subscription, timer } from 'rxjs';
import { catchError, finalize, map, switchMap } from 'rxjs/operators';

interface WatchlistApiItem {
    ticker: string;
    added_at: string;
}

interface WatchlistItem {
    ticker: string;
    name: string;         // FIX: non-optional — we always supply a fallback
    current_price: number;
    change: number;
    change_pct: number;
    volume: number;
}

interface StockPrice  { latestPrice?: number; }
interface StockMetric {
    market_cap?: string | number;
    pe_ratio?: string | number;
    dividend_yield?: number;
    volume?: string | number;  // FIX: typed as optional — backend returns '' on missing fields
    shortName?: string;
}
interface StockChange {
    change_amt?: number;
    change_pct?: number;
}

@Component({
    selector: 'watchlist',
    standalone: true,
    imports: [CommonModule, FormsModule, RouterModule],
    templateUrl: './watchlist.component.html',
    styleUrls: ['./watchlist.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WatchlistComponent implements OnInit, OnDestroy {
    private http       = inject(HttpClient);
    private auth       = inject(AuthService);
    private platformId = inject(PLATFORM_ID);
    private apiUrl     = '/api';

    watchlistItems = signal<WatchlistItem[]>([]);
    newTicker      = signal('');
    infoMessage    = signal<{ type: 'error' | 'success'; text: string } | null>(null);
    isLoading      = signal(true);
    isAdding       = signal(false);

    private refreshSubscription: Subscription | null = null;

    ngOnInit(): void {
        if (isPlatformBrowser(this.platformId)) {
            this.fetchWatchlistAndDetails();
            this.refreshSubscription = timer(60_000, 60_000).subscribe(() =>
                this.fetchWatchlistAndDetails(false)
            );
        } else {
            this.isLoading.set(false);
        }
    }

    ngOnDestroy(): void {
        this.refreshSubscription?.unsubscribe();
    }

    fetchWatchlistAndDetails(showLoading = true): void {
        const userId = this.auth.currentUserId();
        if (!userId) {
            this.infoMessage.set({ type: 'error', text: 'User not logged in.' });
            this.isLoading.set(false);
            return;
        }

        if (showLoading) {
            this.isLoading.set(true);
            this.infoMessage.set(null);
        }

        this.http
            .get<WatchlistApiItem[]>(`${this.apiUrl}/watchlist/${userId}`, { withCredentials: true })
            .pipe(
                switchMap((apiItems) => {
                    if (!apiItems?.length) return of([] as WatchlistItem[]);

                    const detailRequests = apiItems.map(({ ticker }) =>
                        forkJoin({
                            price: this.http
                                .get<StockPrice>(`${this.apiUrl}/stock/${ticker}`, { withCredentials: true })
                                .pipe(catchError(() => of({} as StockPrice))),
                            metrics: this.http
                                .get<StockMetric>(`${this.apiUrl}/metrics/${ticker}`, { withCredentials: true })
                                .pipe(catchError(() => of({} as StockMetric))),
                            info: this.http
                                .get<StockChange>(`${this.apiUrl}/change/${ticker}`, { withCredentials: true })
                                .pipe(catchError(() => of({} as StockChange))),
                        }).pipe(
                            map(({ price, metrics, info }) => {
                                // FIX: parse volume safely — backend may return a formatted
                                // string like "1,234,567.00" OR a raw number OR undefined.
                                // Previously parseInt(undefined.replace(...)) threw; now we
                                // handle all three cases explicitly.
                                const rawVolume = metrics?.volume;
                                let volume = 0;
                                if (typeof rawVolume === 'number') {
                                    volume = Math.round(rawVolume);
                                } else if (typeof rawVolume === 'string') {
                                    // strip commas and trailing decimal part, then parse
                                    volume = parseInt(rawVolume.replace(/,/g, ''), 10) || 0;
                                }

                                return {
                                    ticker,
                                    // FIX: always provide a string — 'undefined' string in the
                                    // UI is worse than showing the ticker symbol as a fallback.
                                    name:          metrics?.shortName ?? ticker,
                                    current_price: price?.latestPrice ?? 0,
                                    change:        info?.change_amt   ?? 0,
                                    change_pct:    info?.change_pct   ?? 0,
                                    volume,
                                } satisfies WatchlistItem;
                            })
                        )
                    );

                    return forkJoin(detailRequests);
                }),
                catchError(err => {
                    console.error('Error fetching watchlist or details:', err);
                    this.infoMessage.set({ type: 'error', text: 'Failed to load watchlist details.' });
                    return of([] as WatchlistItem[]);
                }),
                finalize(() => {
                    if (showLoading || this.isLoading()) this.isLoading.set(false);
                })
            )
            .subscribe(items => this.watchlistItems.set(items));
    }

    addTicker(): void {
        const userId = this.auth.currentUserId();
        if (!userId) {
            this.infoMessage.set({ type: 'error', text: 'User not logged in.' });
            return;
        }

        const tickerToAdd = this.newTicker().trim().toUpperCase();
        if (!tickerToAdd) {
            this.infoMessage.set({ type: 'error', text: 'Please enter a ticker symbol.' });
            setTimeout(() => this.infoMessage.set(null), 3000);
            return;
        }

        if (this.watchlistItems().some(i => i.ticker === tickerToAdd)) {
            this.infoMessage.set({ type: 'error', text: `${tickerToAdd} is already in the watchlist.` });
            setTimeout(() => this.infoMessage.set(null), 3000);
            return;
        }

        this.isAdding.set(true);
        this.infoMessage.set(null);

        this.http
            .post<any>(`${this.apiUrl}/watchlist/${userId}`, { ticker: tickerToAdd }, { withCredentials: true })
            .pipe(
                catchError(err => {
                    this.infoMessage.set({ type: 'error', text: err.error?.detail ?? `Failed to add ${tickerToAdd}.` });
                    setTimeout(() => this.infoMessage.set(null), 3000);
                    return of(null);
                }),
                finalize(() => this.isAdding.set(false))
            )
            .subscribe(response => {
                if (response) {
                    this.infoMessage.set({ type: 'success', text: response.message ?? `${tickerToAdd} added successfully.` });
                    this.newTicker.set('');
                    this.fetchWatchlistAndDetails(false);
                    setTimeout(() => this.infoMessage.set(null), 3000);
                }
            });
    }

    removeTicker(tickerToRemove: string): void {
        const userId = this.auth.currentUserId();
        if (!userId) {
            this.infoMessage.set({ type: 'error', text: 'User not logged in.' });
            return;
        }

        this.infoMessage.set(null);

        this.http
            .delete<any>(`${this.apiUrl}/watchlist/${userId}/${tickerToRemove}`, { withCredentials: true })
            .pipe(
                catchError(err => {
                    this.infoMessage.set({ type: 'error', text: err.error?.detail ?? `Failed to remove ${tickerToRemove}.` });
                    setTimeout(() => this.infoMessage.set(null), 3000);
                    return of(null);
                })
            )
            .subscribe(response => {
                if (response) {
                    this.infoMessage.set({ type: 'success', text: response.message ?? `${tickerToRemove} removed.` });
                    this.fetchWatchlistAndDetails(false);
                    setTimeout(() => this.infoMessage.set(null), 3000);
                }
            });
    }
}