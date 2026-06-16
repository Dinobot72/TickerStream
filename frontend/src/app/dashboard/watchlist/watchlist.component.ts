import { ChangeDetectionStrategy, Component, signal, OnInit, OnDestroy, inject, PLATFORM_ID } from "@angular/core"; // Added OnInit, OnDestroy, inject
import { CommonModule, isPlatformBrowser, CurrencyPipe, PercentPipe } from "@angular/common"; // Added isPlatformBrowser, Pipes
import { FormsModule } from "@angular/forms";
import { RouterModule } from "@angular/router";
import { HttpClient } from "@angular/common/http"; // Added HttpClient
import { AuthService } from "../../auth.service"; // Added AuthService
import { forkJoin, of, Subscription, timer } from "rxjs"; // Added forkJoin, of, Subscription, timer
import { catchError, finalize, map, switchMap, tap } from 'rxjs/operators'; // Added RxJS operators

interface WatchlistApiItem {
    ticker: string;
    added_at: string; // Or Date if backend converts
}

interface WatchlistItem {
    ticker: string;
    name?: string; // Optional name from metrics
    current_price: number;
    change: number;
    change_pct: number;
    volume: number; // Use number for consistency
}

// Interfaces for API responses
interface StockPrice {
    latestPrice?: number;
}
interface StockMetric {
     market_cap: string;
     pe_ratio: string;
     dividend_yield: number;
     volume: string; // Backend formats with commas
     shortName?: string; // yfinance info often has shortName
}

interface StockChange {
    change_amt: number;
    change_pct: number;
}


@Component({
    selector: 'watchlist',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        RouterModule,
        CurrencyPipe, // Add pipes
        PercentPipe
    ],
    templateUrl: './watchlist.component.html',
    styleUrls: ['./watchlist.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush,
})

export class WatchlistComponent implements OnInit, OnDestroy { // Implements OnInit, OnDestroy
    private http = inject(HttpClient);
    private auth = inject(AuthService);
    private platformId = inject(PLATFORM_ID);
    private apiUrl = '/api';

    watchlistItems = signal<WatchlistItem[]>([]);
    newTicker = signal('');
    infoMessage = signal<{type: 'error' | 'success', text: string} | null>(null);
    isLoading = signal(true); // Loading state for initial fetch + updates
    isAdding = signal(false); // Specific loading state for adding

    private refreshSubscription: Subscription | null = null;


    ngOnInit(): void {
        if (isPlatformBrowser(this.platformId)) {
            this.fetchWatchlistAndDetails();
            // Set up auto-refresh every 60 seconds
            this.refreshSubscription = timer(60000, 60000).subscribe(() => {
                this.fetchWatchlistAndDetails(false); // Refresh details without initial load indicator
            });
        } else {
             this.isLoading.set(false);
        }
    }

    ngOnDestroy(): void {
        this.refreshSubscription?.unsubscribe();
    }

    fetchWatchlistAndDetails(showLoading: boolean = true): void {
        const userId = this.auth.currentUserId();
        if (!userId) {
            this.infoMessage.set({ type: 'error', text: 'User not logged in.' });
            this.isLoading.set(false);
            return;
        }

        if (showLoading) {
            this.isLoading.set(true);
            this.infoMessage.set(null); // Clear previous messages
        }

        // 1. Fetch the list of tickers in the watchlist
        this.http.get<WatchlistApiItem[]>(`${this.apiUrl}/watchlist/${userId}`, { withCredentials: true })
            .pipe(
                switchMap((apiItems: WatchlistApiItem[]) => {
                    if (!apiItems || apiItems.length === 0) {
                        return of([] as WatchlistItem[]); // Return empty array if watchlist is empty
                    }
                    const tickers = apiItems.map(item => item.ticker);

                    // 2. Create requests to fetch details (price & metrics) for each ticker
                    const detailRequests = tickers.map(ticker => 
                        forkJoin({
                            price: this.http.get<StockPrice>(`${this.apiUrl}/stock/${ticker}`, { withCredentials: true }).pipe(catchError(() => of({ latestPrice: 0 }))),
                            metrics: this.http.get<StockMetric>(`${this.apiUrl}/metrics/${ticker}`, { withCredentials: true }).pipe(catchError(() => of({} as StockMetric))),
                            info: this.http.get<StockChange>(`${this.apiUrl}/change/${ticker}`, { withCredentials: true }).pipe(catchError(() => of({} as StockChange)))
                        }).pipe(
                            map(details => ({ // Combine results for this ticker
                                ticker: ticker,
                                name: details.metrics?.shortName, // Get name from metrics if available
                                current_price: details.price?.latestPrice ?? 0,
                                // Calculate change based on previous close (if available in metrics, else approximation)
                                // Placeholder calculation: assume metrics include previous close or calculate based on open
                                change: details.info?.change_amt ?? 0, // TODO: Calculate change properly if data allows
                                change_pct: details.info?.change_pct ?? 0, // TODO: Calculate change % properly
                                volume: parseInt((details.metrics?.volume || '0').replace(/,/g, ''), 10) || 0, // Parse volume string
                            }))
                        )
                    );
                    
                    // 3. Execute all detail requests in parallel
                    return forkJoin(detailRequests);
                }),
                catchError(err => {
                    console.error('Error fetching watchlist or details:', err);
                    this.infoMessage.set({ type: 'error', text: 'Failed to load watchlist details.' });
                    return of([] as WatchlistItem[]); // Return empty on error
                }),
                finalize(() => {
                     if (showLoading || this.isLoading()) {
                        this.isLoading.set(false);
                     }
                })
            )
            .subscribe(detailedItems => {
                this.watchlistItems.set(detailedItems);
            });
    }


    addTicker(): void {
        const userId = this.auth.currentUserId();
         if (!userId) {
            this.infoMessage.set({type: 'error', text: 'User not logged in.'});
            return;
        }

        const tickerToAdd = this.newTicker().trim().toUpperCase();
        if (!tickerToAdd) {
            this.infoMessage.set({type: 'error', text: 'Please enter a ticker symbol.'});
            setTimeout(() => this.infoMessage.set(null), 3000); // Clear message
            return;
        }

        if (this.watchlistItems().some(item => item.ticker === tickerToAdd)) {
            this.infoMessage.set({type: 'error', text: `${tickerToAdd} is already in the watchlist.`});
            setTimeout(() => this.infoMessage.set(null), 3000);
            return;
        }

        this.isAdding.set(true);
        this.infoMessage.set(null);

        this.http.post<any>(`${this.apiUrl}/watchlist/${userId}`, { ticker: tickerToAdd }, { withCredentials: true })
            .pipe(
                catchError(err => {
                    console.error("Failed to add ticker:", err);
                    this.infoMessage.set({type: 'error', text: err.error?.detail || `Failed to add ${tickerToAdd}.`});
                    setTimeout(() => this.infoMessage.set(null), 3000);
                    return of(null); // Keep stream alive
                }),
                finalize(() => this.isAdding.set(false))
            )
            .subscribe(response => {
                if (response) { // Check if the request was successful (not caught by catchError)
                    this.infoMessage.set({type: 'success', text: response.message || `${tickerToAdd} added successfully.`});
                    this.newTicker.set(''); // Clear input
                    this.fetchWatchlistAndDetails(false); // Refresh the list without full loading indicator
                    setTimeout(() => this.infoMessage.set(null), 3000);
                }
            });
    }

    removeTicker(tickerToRemove: string): void {
         const userId = this.auth.currentUserId();
         if (!userId) {
            this.infoMessage.set({type: 'error', text: 'User not logged in.'});
            return;
        }
        
        // Optimistic UI update (optional)
        // const currentItems = this.watchlistItems();
        // this.watchlistItems.set(currentItems.filter(item => item.ticker !== tickerToRemove));
        this.infoMessage.set(null); // Clear previous message

        this.http.delete<any>(`${this.apiUrl}/watchlist/${userId}/${tickerToRemove}`, { withCredentials: true })
             .pipe(
                catchError(err => {
                    console.error(`Failed to remove ${tickerToRemove}:`, err);
                    this.infoMessage.set({type: 'error', text: err.error?.detail || `Failed to remove ${tickerToRemove}.`});
                    // Revert optimistic update if used
                    // this.watchlistItems.set(currentItems); 
                     setTimeout(() => this.infoMessage.set(null), 3000);
                    return of(null);
                })
            )
            .subscribe(response => {
                if (response) {
                    this.infoMessage.set({type: 'success', text: response.message || `${tickerToRemove} removed.`});
                     this.fetchWatchlistAndDetails(false); // Refresh the list fully after successful removal
                     setTimeout(() => this.infoMessage.set(null), 3000);
                }
            });
    }
}
