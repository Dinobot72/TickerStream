import { CommonModule, isPlatformBrowser } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, signal, OnInit, Injectable, Input, inject, PLATFORM_ID } from '@angular/core';
import { MatGridListModule } from '@angular/material/grid-list';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { AuthService } from '../../auth.service';

interface Holding {
    ticker: string;
    quantity: number;
    purchase_price: number;
} 

interface Activity {
    action: string;
    ticker: string;
    quantity: string;
    price: number;
    is_bot_trade: boolean;
}

@Component({
    selector: 'main-content',
    standalone: true,
    imports: [
        CommonModule,
        MatGridListModule,
        MatButtonModule,
    ],
    templateUrl: './main-content.component.html',
    styleUrls: ['./main-content.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush,

})
export class MainContentComponent implements OnInit {

    private apiUrl = 'http://localhost:8000/api'; 
    private platformId = inject(PLATFORM_ID);

    public portfolioValue = signal(0);
    public userBalance = signal(0);
    public portfolioHoldings = signal<Holding[]>([]);

    public ticker = "AAPL";
    public marketCap = signal(0);
    public peRatio = signal(0);
    public dividendYield = signal(0);
    public volume = signal(0);

    public botStatus = signal('Idle');
    public botActivity = signal<Activity[]>([]);

    @Input() userName: string = 'User';
    

    // portfolioPercentage = computed(() => {
    //     const target = 50000;
    //     return Math.floor((this.portfolioValue() / target) * 100);
    // });
    portfolioProgress = computed(() => {
        const circumference = 251.2;
        return circumference - (circumference * this.portfolioChange()) / 100;
    });

    portfolioChange = computed(() => {
        const totalValue = this.portfolioValue();
        const initialValue = this.portfolioHoldings().reduce((acc, holding) => acc + (holding.quantity * holding.purchase_price), 0);
        if (initialValue === 0) return 0;
        return ((totalValue - initialValue) / initialValue) * 100;
    })

    constructor(private http: HttpClient, private authService: AuthService) {}

    ngOnInit(): void {
        if (isPlatformBrowser(this.platformId)) {
            this.fetchUserData();
            this.fetchPortfolio();
            this.fetchMetrics();
            this.fetchActivity();
        }
    }

    fetchUserData(): void {
        const userId = this.authService.getUserId();
        if (!userId) return;
        this.http.get<any>(`${this.apiUrl}/user/${userId}`).subscribe({
            next: (data) => {
                this.userBalance.set(data.balance);
            },
            error: (err) => console.error('Failed to fetch user data', err)
        });
    }

    fetchPortfolio(): void {
        const userId = this.authService.getUserId();
        if (!userId) return;

        this.http.get<Holding[]>(`${this.apiUrl}/holdings/${userId}`).subscribe({
            next: (data) => {
                this.portfolioHoldings.set(data);
                // Simple calculation for portfolio value (can be improved by fetching live prices for all holdings)
                const totalValue = data.reduce((acc, holding) => acc + (holding.quantity * holding.purchase_price), 0);
                this.portfolioValue.set(totalValue);
            },
            error: (err) => {
                console.error('Failed to fetch portfolio', err);
            }
        })
    }

    fetchMetrics(): void {
        this.http.get<any>(`${this.apiUrl}/metrics/${this.ticker}`).subscribe({
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
        const userId = this.authService.getUserId();
        if (!userId) return;
        this.http.get<Activity[]>(`${this.apiUrl}/activity/${userId}`).subscribe({
            next: (data) => this.botActivity.set(data),
            error: (err) => console.error('Failed to fetch activity', err)
        });
    }

    deposit(): void {
        const amountStr = prompt("Enter amount to deposit:", "1000");
        if (amountStr) {
            const amount = parseFloat(amountStr);
            const userId = this.authService.getUserId();
            if (!isNaN(amount) && amount > 0 && userId) {
                this.http.post<any>(`${this.apiUrl}/user/${userId}/deposit`, { amount }).subscribe({
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
        const userId = this.authService.getUserId();
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
                // Here you could add logic to automatically execute the trade
                // For now, we just show the decision.
            },
            error: (err) => {
                this.botStatus.set('Error!');
                console.error('Bot decision failed', err);
            }
        });
    }
}