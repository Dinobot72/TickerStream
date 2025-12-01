import { CommonModule, isPlatformBrowser } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, signal, OnInit, Injectable, Input, inject, PLATFORM_ID } from '@angular/core';
import { RouterModule, Router, NavigationEnd } from '@angular/router'; // Added RouterModule and Router for navigation/link
import { HttpClient } from '@angular/common/http'; // Added HttpClient for API calls
import { MatGridListModule } from '@angular/material/grid-list'; // Preserved old imports
import { MatButtonModule } from '@angular/material/button'; // Preserved old imports
// Assuming AuthService is available in the project structure
import { AuthService } from '../../auth.service'; 
import { BotStatusService } from '../../services/bot-status.service';
import { catchError, forkJoin, map, Observable, of, switchMap } from 'rxjs';

// Define interface for Holding data (Same as old, matched new structure)
interface Holding {
    ticker: string;
    quantity: number;
    purchase_price: number;
}

// Define interface for Activity data (Merged: Used new fields/types, added old file's implicit field)
interface Activity {
    action: 'BUY' | 'SELL' | string; // Keep string to allow non-enum actions from API
    ticker: string;
    quantity: number; // Changed to number to match new file and for calculation ease
    price: number;
    is_bot_trade: boolean;
    timestamp?: string; // Made optional as old Activity interface didn't have it
}

// Interface for Market data (From new file)
interface MarketIndex {
    name: string;
    value: number;
    change: number;
    changePct: number;
}

// Interface for Trending data (From new file)
interface TrendingStock {
    ticker: string;
    price: number;
    changePct: number;
}

@Component({
    selector: 'homepage', // Use the new selector
    standalone: true,
    imports: [
        CommonModule,
        RouterModule, // For routerLink
        MatGridListModule, // Preserved old import
        MatButtonModule, // Preserved old import
    ],
    templateUrl: './homepage.component.html',
    styleUrls: ['./homepage.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HomepageComponent implements OnInit {

    // --- Injected Dependencies (From previous file) ---
    private apiUrl = 'http://localhost:8000/api'; 
    private router = inject(Router);
    private platformId = inject(PLATFORM_ID);
    isBotActive: Observable<boolean>;


    
    // Injected into constructor from previous file
    constructor(
        private http: HttpClient,
        private authService: AuthService,
        private botStatusService: BotStatusService
    ) {
        this.isBotActive = this.botStatusService.botStatus$
    } 

    // --- Component State/Data ---

    // USER INFO (Merged: Preserved @Input for compatibility, but also using signal)
    userName = signal('User');
    userBalance = signal(10000.00); // Merged: Use new initial value, but old signal name

    // PORTFOLIO DATA (Merged: Use new initial data structure, but old signal names)
    portfolioHoldings = signal<Holding[]>([
        { ticker: 'AAPL', quantity: 10, purchase_price: 150.00 },
        { ticker: 'MSFT', quantity: 5, purchase_price: 300.00 },
    ]);
    portfolioValue = signal(0); // From old file (will be updated by fetchPortfolio)

    // LIVE DATA (From new file)
    currentPrices = signal(new Map<string, number>([
        ['AAPL', 175.00],
        ['MSFT', 320.00],
    ]));
    
    marketIndices = signal<MarketIndex[]>([
        { name: 'S&P 500', value: 4500.50, change: 15.20, changePct: 0.34 },
        { name: 'NASDAQ', value: 14000.75, change: -5.10, changePct: -0.04 },
        { name: 'DOW JONES', value: 35000.00, change: 50.00, changePct: 0.14 },
    ]);
    
    trendingStocks = signal<TrendingStock[]>([
        { ticker: 'GME', price: 25.50, changePct: 10.5 },
        { ticker: 'AMC', price: 5.80, changePct: 8.2 },
        { ticker: 'NVDA', price: 950.00, changePct: 2.1 },
    ]);

    // METRICS (From previous file)
    public ticker = "AAPL";
    public marketCap = signal(0);
    public peRatio = signal(0);
    public dividendYield = signal(0);
    public volume = signal(0);

    // ACTIVITY / BOT STATUS (Merged: Use new signal for activity, but old signal for bot status)
    recentActivity = signal<Activity[]>([
        { action: 'BUY', ticker: 'AAPL', quantity: 10, price: 150.00, is_bot_trade: false, timestamp: '2025-10-25T10:30:00Z' },
        { action: 'BUY', ticker: 'MSFT', quantity: 5, price: 300.00, is_bot_trade: false, timestamp: '2025-10-24T14:15:00Z' },
        { action: 'SELL', ticker: 'TSLA', quantity: 2, price: 250.00, is_bot_trade: true, timestamp: '2025-10-24T09:05:00Z' },
    ]);
    botActivity = signal<Activity[]>([]); // Preserved old signal
    botStatus = signal('Idle'); // From old file (used in getBotDecision)

    // --- Computed Values ---

    // New file's Portfolio Value (Uses currentPrices) - Renamed to distinguish from old signal
    portfolioValueLive = computed(() => {
        const prices = this.currentPrices();
        return this.portfolioHoldings().reduce((acc, holding) => {
            // Use current price if available, otherwise use purchase price
            const currentPrice = prices.get(holding.ticker) || holding.purchase_price; 
            return acc + (holding.quantity * currentPrice);
        }, 0);
    });

    // Old file's Portfolio Change (Needed for old HTML's gauge)
    portfolioChange = computed(() => {
        const totalValue = this.portfolioValue();
        const initialValue = this.portfolioHoldings().reduce((acc, holding) => acc + (holding.quantity * holding.purchase_price), 0);
        if (initialValue === 0) return 0;
        return ((totalValue - initialValue) / initialValue) * 100;
    })

    // Old file's Portfolio Progress (Needed for old HTML's gauge)
    portfolioProgress = computed(() => {
        const circumference = 251.2;
        return circumference - (circumference * this.portfolioChange()) / 100;
    });

    // New file's Portfolio Cost Basis
    portfolioCostBasis = computed(() => {
        return this.portfolioHoldings().reduce((acc, holding) => acc + (holding.quantity * holding.purchase_price), 0);
    });

    // New file's Total P/L (Uses portfolioValueLive)
    totalPortfolioPL = computed(() => {
        return this.portfolioValueLive() - this.portfolioCostBasis();
    });

    // New file's Total P/L Percentage (Uses portfolioValueLive)
    totalPortfolioPLPct = computed(() => {
        const costBasis = this.portfolioCostBasis();
        if (costBasis === 0) return 0;
        return (this.totalPortfolioPL() / costBasis) * 100;
    });

    // --- Dropdown State and Methods (From new file) ---
    isUserMenuOpen = signal(false);
    toggleUserMenu(): void {
        this.isUserMenuOpen.update(open => !open);
    }
    closeUserMenu(): void {
        this.isUserMenuOpen.set(false);
    }

    // --- Lifecycle Hook (From previous file) ---
    ngOnInit(): void {
        if (isPlatformBrowser(this.platformId)) {
            this.fetchUserData();
            this.fetchPortfolio();
            this.fetchMetrics();
            this.fetchActivity();
        }
    }

    // --- API and Utility Methods (Preserved from previous file) ---
    fetchUserData(): void {
        const userId = this.authService.currentUserId();
        if (!userId) return;
        this.http.get<any>(`${this.apiUrl}/user/${userId}`, {withCredentials: true}).subscribe({
            next: (data) => {
                console.log('Fetched user data:', data);
                this.userBalance.set(data.balance);
                this.userName.set(data.first_name);
            },
            error: (err) => console.error('Failed to fetch user data', err)
        });
    }

    fetchPortfolio(): void {
        const userId = this.authService.currentUserId();
        if (!userId) return;

        this.http.get<Holding[]>(`${this.apiUrl}/holdings/${userId}`, { withCredentials: true })
            .pipe(
                switchMap((holdings: Holding[]) => {
                    // 1. Handle empty portfolio
                    if (!holdings || holdings.length === 0) {
                        return of({ holdings: [], prices: new Map<string, number>() });
                    }

                    // 2. Get unique tickers
                    const uniqueTickers = [...new Set(holdings.map(h => h.ticker))];

                    // 3. Request prices using the /stock/ endpoint (from your first snippet)
                    const priceRequests = uniqueTickers.map(ticker =>
                        this.http.get<any>(`${this.apiUrl}/stock/${ticker}`, { withCredentials: true }).pipe(
                            map(response => {
                                // Match the field 'latestPrice' from your first snippet
                                const price = response?.latestPrice ?? 0; 
                                return { ticker, price };
                            }),
                            catchError(err => {
                                console.error(`Failed to fetch price for ${ticker}`, err);
                                return of({ ticker, price: 0 }); // Default to 0 on error
                            })
                        )
                    );

                    // 4. Execute all requests in parallel
                    return forkJoin(priceRequests).pipe(
                        map(priceResults => {
                            const prices = new Map<string, number>();
                            priceResults.forEach(result => {
                                if (result.price > 0) {
                                    prices.set(result.ticker, result.price);
                                }
                            });
                            return { holdings, prices };
                        })
                    );
                }),
                catchError(err => {
                    console.error('Error fetching portfolio:', err);
                    return of({ holdings: [], prices: new Map<string, number>() });
                })
            )
            .subscribe(({ holdings, prices }) => {
                // 5. Update signals
                this.portfolioHoldings.set(holdings);
                this.currentPrices.set(prices);
                
                // (Optional) Update the legacy signal for debugging
                const totalVal = holdings.reduce((acc, h) => {
                    const price = prices.get(h.ticker) ?? h.purchase_price;
                    return acc + (h.quantity * price);
                }, 0);
                
                console.log('Portfolio updated. Total Value:', totalVal);
                this.portfolioValue.set(totalVal);
            });
    }

    fetchMetrics(): void {
        this.http.get<any>(`${this.apiUrl}/metrics/${this.ticker}`, {withCredentials: true}).subscribe({
            next: (data) => {
                this.marketCap.set(data.market_cap);
                this.peRatio.set(data.pe_ratio)
                this.volume.set(data.volume)
                this.dividendYield.set(data.dividend_yield)
            },
            error: (err) => console.error('Failed to fetch metrics', err)
        })
    }
    
    fetchActivity(): void {
        const userId = this.authService.currentUserId();
        if (!userId) return;
        this.http.get<Activity[]>(`${this.apiUrl}/activity/${userId}`, {withCredentials: true}).subscribe({
            next: (data) => {
                // Update both old and new activity signals (only new one is likely used in the merged HTML)
                this.botActivity.set(data);
                this.recentActivity.set(data);
            },
            error: (err) => console.error('Failed to fetch activity', err)
        });
    }

    deposit(): void {
        const amountStr = prompt("Enter amount to deposit:", "1000");
        if (amountStr) {
            const amount = parseFloat(amountStr);
            const userId = this.authService.currentUserId();
            if (!isNaN(amount) && amount > 0 && userId) {
                this.http.post<any>(`${this.apiUrl}/user/${userId}/deposit`, { amount }, {withCredentials: true}).subscribe({
                    next: (res) => {
                        this.userBalance.set(res.new_balance);
                        alert(`Deposit successful. New balance: $${res.new_balance.toFixed(2)}`);
                    },
                    error: (err) => {
                        console.error('Deposit failed', err);
                        alert('Deposit failed. Please try again.');
                    }
                });
            } else {
                alert("Invalid amount.");
            }
        }
    }
    
    getBotDecision(): void {
        const userId = this.authService.currentUserId();
        if (!userId) return;

        const aaplHolding = this.portfolioHoldings().find(h => h.ticker === 'AAPL');
        const sharesHeld = aaplHolding ? aaplHolding.quantity : 0;
        
        const state = {
            balance: this.userBalance(),
            shares_held: sharesHeld
        };

        this.botStatus.set('Thinking...');
        this.http.post<any>(`${this.apiUrl}/bot/decision`, state).subscribe({
            next: (res) => {
                const decision = res.decision;
                this.botStatus.set(`Decision: ${decision}`);
                alert(`Bot has decided to: ${decision}`);
            },
            error: (err) => {
                this.botStatus.set('Error!');
                console.error('Bot decision failed', err);
            }
        });
    }
    
    logOut(): void {
        console.log('Loggin out');
        this.http.post<any>(`${this.apiUrl}/logout`, {}, { withCredentials: true }).subscribe({
            next: (res) => {
                this.router.navigate(['/login']);
                console.log(res);
            },
            error: (err) => {
                console.log(err);
                this.router.navigate(['/login']); 
            }
        })
    }
}