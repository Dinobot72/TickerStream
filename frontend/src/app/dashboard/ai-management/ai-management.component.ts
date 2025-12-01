import { ChangeDetectionStrategy, Component, inject, OnInit, Signal, signal } from '@angular/core';
import { CommonModule, CurrencyPipe, DatePipe, PercentPipe } from '@angular/common';
import { AuthService } from '../../auth.service';
import { HttpClient } from '@angular/common/http';
import { catchError, finalize, map, of, tap, Observable } from 'rxjs';
import { BotStatusService } from '../../services/bot-status.service';


interface Activity {
  action: 'BUY' | 'SELL';
  ticker: string;
  quantity: number;
  price: number;
  timestamp: string;
  is_bot_trade: boolean;
}

interface BotStatus {
  status: string;
  message?: string;
}

@Component({
  selector: 'ai-management',
  standalone: true,
  imports: [
    CommonModule,
    DatePipe,
    CurrencyPipe,
    PercentPipe,
  ],
  templateUrl: './ai-management.component.html',
  styleUrls: ['./ai-management.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiManagementComponent implements OnInit {

  private http = inject(HttpClient);
  private auth = inject(AuthService);
  private apiUrl = 'http://localhost:8000/api';

  // --- Bot Status ---
  // isBotActive: Observable<boolean>;
  isBotActive = signal(false);
  botStatusMessage = signal('Fetching status...');
  lastActionTime = signal<string | null>(null); // Track last bot action time
  isUpdatingStatus = signal(false);

  // --- Bot Activity Log ---
  botActivityLog = signal<Activity[]>([]);
  isLoadingActivity = signal(true); // Start loading initially
  activityError = signal<string | null>(null);

  // --- Bot Performance (Calculated) ---
  botTotalPL = signal(0);
  botWinRate = signal(0); // Store as number 0-1
  botTradesCount = signal(0);

  // --- Configuration (Placeholders - TODO: fetch/update via API if needed) ---
  riskLevel = signal<'Low' | 'Medium' | 'High'>('Medium');
  allowedTickers = signal('AAPL, MSFT, GOOGL');

  constructor(private botStatusService: BotStatusService
    ) {
      // this.isBotActive = this.botStatusService.botStatus$
    } 


  ngOnInit(): void {
    this.fetchBotStatus();
    this.fetchBotActivity();
  }


  fetchBotStatus(): void {
    this.isUpdatingStatus.set(true); // Indicate loading for status check
    this.http.get<BotStatus>(`${this.apiUrl}/bot/status`, { withCredentials: true })
      .pipe(
        catchError(err => {
          console.error('Failed to fetch bot status:', err);
          this.botStatusMessage.set('Error fetching status.');
          this.isBotActive.set(false);
          return of(null); // Continue stream
        }),
        finalize(() => this.isUpdatingStatus.set(false))
      )
      .subscribe(status => {
        if (status) {
          this.isBotActive.set(status.status === 'active');
          this.botStatusMessage.set(status.message || (status.status === 'active' ? 'Actively monitoring' : 'Inactive'));
        }
      });
  }

  fetchBotActivity(): void {
    const userId = this.auth.currentUserId();
    if (!userId) {
      this.activityError.set("User not logged in.");
      this.isLoadingActivity.set(false);
      return;
    }

    this.isLoadingActivity.set(true);
    this.activityError.set(null);

    this.http.get<Activity[]>(`${this.apiUrl}/activity/${userId}?limit=50`, { withCredentials: true }) // Fetch more for calculation
      .pipe(
        map(activities => activities.filter(a => a.is_bot_trade)), // Filter only bot trades
        tap(botActivities => {
          this.botActivityLog.set(botActivities.slice(0, 10)); // Display latest 10
          this.calculatePerformance(botActivities);
          if (botActivities.length > 0) {
            this.lastActionTime.set(botActivities[0].timestamp); // Assuming sorted descending
          } else {
            this.lastActionTime.set(null);
          }
        }),
        catchError(err => {
          console.error("Failed to fetch bot activity:", err);
          this.activityError.set("Could not load bot activity.");
          this.botActivityLog.set([]); // Clear log on error
          return of([] as Activity[]); // Return empty array to keep stream alive
        }),
        finalize(() => this.isLoadingActivity.set(false))
      )
      .subscribe();
  }

  toggleBotStatus(): void {
    const endpoint = this.isBotActive() ? `${this.apiUrl}/bot/stop` : `${this.apiUrl}/bot/start`;
    const optimisticStatus = !this.isBotActive(); // What we expect the status to become

    this.isUpdatingStatus.set(true); // Show loading
    this.botStatusMessage.set(optimisticStatus ? 'Starting bot...' : 'Stopping bot...');

    this.http.post<BotStatus>(endpoint, {}, { withCredentials: true })
      .pipe(
        catchError(err => {
          console.error(`Failed to ${optimisticStatus ? 'start' : 'stop'} bot:`, err);
          this.botStatusMessage.set(`Error ${optimisticStatus ? 'starting' : 'stopping'} bot.`);
          // Revert optimistic update on error
          this.isBotActive.set(!optimisticStatus);
          return of(null);
        }),
        finalize(() => this.isUpdatingStatus.set(false))
      )
      .subscribe(status => {
        if (status) {
          // Update based on actual response
          this.isBotActive.set(status.status === 'active');
          this.botStatusMessage.set(status.message || (status.status === 'active' ? 'Actively monitoring' : 'Inactive'));
        } else {
          // If error occurred and was caught, status might be null
          // Status message and active state should already be reverted by catchError
        }
      });
  }


  calculatePerformance(activities: Activity[]): void {
    if (!activities || activities.length === 0) {
      this.botTotalPL.set(0);
      this.botWinRate.set(0);
      this.botTradesCount.set(0);
      return;
    }

    // --- Simple P/L Calculation (Example - Needs Refinement) ---
    // This is a basic example and doesn't account for open positions, fees accurately etc.
    // A proper calculation would likely need more data or backend support.
    let simplePL = 0;
    let winningTrades = 0;
    const tradesByTicker: { [key: string]: { buyPrice: number, buyQty: number }[] } = {};

    // Process trades roughly chronologically (assuming API returns newest first)
    for (let i = activities.length - 1; i >= 0; i--) {
      const trade = activities[i];
      if (!tradesByTicker[trade.ticker]) {
        tradesByTicker[trade.ticker] = [];
      }

      if (trade.action === 'BUY') {
        tradesByTicker[trade.ticker].push({ buyPrice: trade.price, buyQty: trade.quantity });
      } else if (trade.action === 'SELL') {
        let sellQty = trade.quantity;
        // Match sells with earliest buys (FIFO approximation)
        while (sellQty > 0 && tradesByTicker[trade.ticker].length > 0) {
          const buyTrade = tradesByTicker[trade.ticker][0];
          const matchQty = Math.min(sellQty, buyTrade.buyQty);

          const pl = (trade.price - buyTrade.buyPrice) * matchQty;
          simplePL += pl;
          if (pl > 0) {
            winningTrades++;
          }

          sellQty -= matchQty;
          buyTrade.buyQty -= matchQty;

          if (buyTrade.buyQty <= 0) {
            tradesByTicker[trade.ticker].shift(); // Remove depleted buy trade
          }
        }
      }
    }

    const totalTrades = activities.length; // Or count pairs for win rate? Depends on definition.
    this.botTotalPL.set(simplePL);
    this.botTradesCount.set(totalTrades);
    this.botWinRate.set(totalTrades > 0 ? winningTrades / totalTrades : 0); // Win rate based on *closed* P/L events
  }

}

