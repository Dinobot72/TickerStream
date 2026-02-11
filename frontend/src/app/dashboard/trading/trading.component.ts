import { ChangeDetectionStrategy, Component, signal, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router'; // To read query params
import { HttpClient } from '@angular/common/http';
import { AuthService } from '../../auth.service';
import { catchError, finalize, of, tap } from 'rxjs';

interface TradePayload {
  user_id: number;
  ticker: string;
  action: 'BUY' | 'SELL';
  quantity: number;
  price: number;
  is_bot_trade: boolean; 
  order_type: 'MARKET' | 'LIMIT';
  limit_price?: number | null;
}

@Component({
  selector: 'app-trading',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './trading.component.html',
  styleUrls: ['./trading.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TradingComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private http = inject(HttpClient);
  private auth = inject(AuthService);
  private apiUrl= 'https://auth.ticker-stream.com/api';
  

  tradeAction = signal<'BUY' | 'SELL'>('BUY');
  ticker = signal('');
  quantity = signal<number | null>(null);
  orderType = signal<'MARKET' | 'LIMIT'>('MARKET');
  limitPrice = signal<number | null>(null);
  
  isSubmitting = signal(false);
  errorMessage = signal<string | null>(null);
  successMessage = signal<string | null>(null);

  // Placeholder for current price
  currentPrice = signal(0.00);

  ngOnInit(): void {
    // Check for ticker in query params
    this.route.queryParams.subscribe(params => {
        if (params['ticker']) {
            this.ticker.set(params['ticker'].toUpperCase());
            // In a real app, you'd fetch the price for this ticker
            this.fetchCurrentPrice(); 
        }
    });
  }

  fetchCurrentPrice(): void {
    const currentTicker = this.ticker().trim().toUpperCase();
    if (!currentTicker) return;

    this.http.get<{ latestPrice?: number }>(`${this.apiUrl}/stock/${currentTicker}`)
      .pipe(
        tap(response => {
          if (response && response.latestPrice !== undefined) {
            this.currentPrice.set(response.latestPrice);
            console.log(`Fetched price for ${currentTicker}: ${response.latestPrice}`);
          } else {
            console.warn(`Could not fetch price for ${currentTicker}`);
            this.currentPrice.set(0);
             this.errorMessage.set(`Could not fetch current price for ${currentTicker}.`);
             setTimeout(() => this.errorMessage.set(null), 4000);
          }
        }),
        catchError(err => {
          console.error('Error fetching stock price:', err);
          this.errorMessage.set(`Error fetching price for ${currentTicker}. Please try again.`);
          this.currentPrice.set(0);
          setTimeout(() => this.errorMessage.set(null), 4000);
          return of(null);
        })
      )
      .subscribe();
  }

  submitTrade(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);

    this.errorMessage.set(null);
    this.successMessage.set(null);

    // --- Basic Validations ---
    const currentTicker = this.ticker().trim().toUpperCase();
    const currentQuantity = this.quantity();
    const currentOrderType = this.orderType();
    const currentLimitPrice = this.limitPrice();
    const currentTradeAction = this.tradeAction();


    if (!currentTicker) {
      this.errorMessage.set('Please enter a ticker symbol.');
      return;
    }
    if (!currentQuantity || currentQuantity <= 0) {
      this.errorMessage.set('Please enter a valid quantity.');
      return;
    }
     if (currentOrderType === 'LIMIT' && (!currentLimitPrice || currentLimitPrice <= 0)) {
        this.errorMessage.set('Please enter a valid limit price for a limit order.');
        return;
    }
     // Ensure price is fetched or available for Market order
    if (currentOrderType === 'MARKET' && this.currentPrice() <= 0) {
         this.errorMessage.set('Current market price is unavailable. Cannot place market order.');
         // Optionally try fetching price again
         // this.fetchCurrentPrice();
         return;
    }


    this.isSubmitting.set(true);

    const userId = this.auth.currentUserId();
    if (!userId) {
        this.errorMessage.set('User not logged in. Cannot place trade.');
        this.isSubmitting.set(false);
        return;
    }

    // Determine the price to use for the trade record
    // For MARKET, use the fetched current price. For LIMIT, use the specified limit price.
    const tradePrice = currentOrderType === 'LIMIT' ? currentLimitPrice! : this.currentPrice();

    // --- Construct the payload for the backend ---
    const tradePayload: TradePayload = {
        user_id: parseInt(userId, 10), // Ensure user_id is a number
        ticker: currentTicker, //
        action: currentTradeAction, //
        quantity: currentQuantity, //
        price: tradePrice, // Use determined price
        is_bot_trade: false, // Manual trade
        order_type: currentOrderType,
        limit_price: currentLimitPrice
    };

    // --- Send the request to the backend ---
    this.http.post<any>(`${this.apiUrl}/trade/`, tradePayload, { withCredentials: true }) // Added withCredentials
      .pipe(
        tap(response => {
          console.log('Trade successful:', response);
          this.successMessage.set(response.message || `Trade submitted successfully: ${currentTradeAction} ${currentQuantity} ${currentTicker}`);
          // Reset form on success
          this.ticker.set('');
          this.quantity.set(null);
          this.limitPrice.set(null);
          this.orderType.set('MARKET'); // Reset to default
          this.currentPrice.set(0); // Reset price display
          // Clear success message after a few seconds
          setTimeout(() => this.successMessage.set(null), 4000);
        }),
        catchError(error => {
          console.error('Trade failed:', error);
          this.errorMessage.set(error.error?.detail || 'Trade submission failed. Please try again.');
          // Clear error message after a few seconds
          setTimeout(() => this.errorMessage.set(null), 4000);
          return of(null); // Prevent error from breaking the stream
        }),
        finalize(() => {
          this.isSubmitting.set(false); // Ensure loading state is turned off
        })
      )
      .subscribe();
    }
}

