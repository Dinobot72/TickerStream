import { ChangeDetectionStrategy, Component, inject, OnDestroy, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { CommonModule, CurrencyPipe, isPlatformBrowser, PercentPipe } from '@angular/common';
import { RouterModule } from '@angular/router'; // Import RouterModule for routerLink
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { HttpClient } from '@angular/common/http';
import { AuthService } from '../../auth.service';
import { forkJoin, of, Subscription, timer } from 'rxjs';
import { catchError, finalize, map, switchMap } from 'rxjs/operators';

// Define interface for Holding data

interface ApiHolding {
  ticker: string;
  quantity: number;
  purchase_price: number;
}

interface DisplayHolding extends ApiHolding{
    // Placeholder for calculated fields
    current_price: number;
    total_value: number;
    total_pl: number;
    total_pl_pct: number;
}

interface StockPrice {
  latestPrice?: number;
}


@Component({
  selector: 'app-positions',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatProgressSpinnerModule,
    CurrencyPipe,
    PercentPipe,
    ],
  templateUrl: './positions.component.html',
  styleUrls: ['./positions.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PositionsComponent implements OnInit, OnDestroy {

  private http = inject(HttpClient);
  private auth = inject(AuthService);
  private platformId = inject(PLATFORM_ID);
  private apiUrl = 'http://localhost:8000/api';
  
  // Placeholder data
  holdings = signal<DisplayHolding[]>([]);
  isLoading = signal(false);
  error = signal<string | null>(null);

  private refreshSubscription: Subscription | null = null;

  ngOnInit(): void {
    if (isPlatformBrowser(this.platformId)) {
        this.fetchHoldingsAndPrices();
        // Set up auto-refresh every 30 seconds
        this.refreshSubscription = timer(30000, 30000).subscribe(() => {
            this.fetchHoldingsAndPrices(false); // Fetch without showing initial loading
        });
    } else {
        this.isLoading.set(false); // Don't show loading on server
    }
  }

  ngOnDestroy(): void {
    this.refreshSubscription?.unsubscribe();
  }

  fetchHoldingsAndPrices(showLoading: boolean = true): void {
    const userId = this.auth.currentUserId();
    if (!userId) {
      this.error.set("User not logged in.");
      this.isLoading.set(false);
      return;
    }

    if (showLoading) {
        this.isLoading.set(true);
        this.error.set(null);
    }

    this.http.get<ApiHolding[]>(`${this.apiUrl}/holdings/${userId}`, { withCredentials: true })
      .pipe(
        switchMap((apiHoldings: ApiHolding[]) => {
          if (!apiHoldings || apiHoldings.length === 0) {
            return of({ holdings: [], prices: new Map<string, number>() }); // Return empty if no holdings
          }

          // Get unique tickers
          const uniqueTickers = [...new Set(apiHoldings.map(h => h.ticker))];
          
          // Create requests to fetch current price for each unique ticker
          const priceRequests = uniqueTickers.map(ticker =>
            this.http.get<StockPrice>(`${this.apiUrl}/stock/${ticker}`, { withCredentials: true }).pipe(
              map(response => ({ ticker, price: response?.latestPrice ?? 0 })), // Default to 0 if fetch fails
              catchError(() => of({ ticker, price: 0 })) // Handle individual price fetch errors
            )
          );

          // Execute all price requests in parallel
          return forkJoin(priceRequests).pipe(
            map(priceResults => {
              const prices = new Map<string, number>();
              priceResults.forEach(result => prices.set(result.ticker, result.price));
              return { holdings: apiHoldings, prices }; // Pass holdings and prices map
            })
          );
        }),
        map(({ holdings, prices }) => {
            // Calculate derived values for each holding
            return holdings.map(h => {
                const current_price = prices.get(h.ticker) ?? h.purchase_price; // Fallback to purchase price if fetch failed
                const total_value = h.quantity * current_price;
                const cost_basis = h.quantity * h.purchase_price;
                const total_pl = total_value - cost_basis;
                const total_pl_pct = cost_basis !== 0 ? (total_pl / cost_basis) : 0;
                
                return {
                    ...h,
                    current_price,
                    total_value,
                    total_pl,
                    total_pl_pct
                } as DisplayHolding;
            });
        }),
        catchError(err => {
          console.error('Error fetching holdings or prices:', err);
          this.error.set('Failed to load positions. Please try again.');
          return of([] as DisplayHolding[]); // Return empty array on error
        }),
        finalize(() => {
          if (showLoading || this.isLoading()) { // Only stop loading if it was started
             this.isLoading.set(false);
          }
        })
      )
      .subscribe(displayHoldings => {
        this.holdings.set(displayHoldings);
      });
  }
}