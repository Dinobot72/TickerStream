import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, signal, OnInit, Injectable, Input } from '@angular/core';
import { MatGridListModule } from '@angular/material/grid-list';
import { HttpClient } from '@angular/common/http';

@Injectable({providedIn: 'root'})

@Component({
    selector: 'main-content',
    standalone: true,
    imports: [
        CommonModule,
        MatGridListModule,
    ],
    templateUrl: './main-content.component.html',
    styleUrls: ['./main-content.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush,

})
export class MainContentComponent implements OnInit {

    private apiUrl = 'http://localhost:8000'; 

    public portfolioValue = signal(0);
    public previousCloseValue = signal(0);
    public ticker = "AAPL";
    public marketCap = signal(0);
    public peRatio = signal(0);
    public dividendYield = signal(0);
    public volume = signal(0);
    public fiftyTwoWeekHigh = signal(0);
    public fiftyTwoWeekLow = signal(0);
    @Input() userName: string = 'User';
    

    portfolioPercentage = computed(() => {
        const target = 50000;
        return Math.floor((this.portfolioValue() / target) * 100);
    });
    portfolioProgress = computed(() => {
        const circumference = 251.2;
        return circumference - (circumference * this.portfolioPercentage()) / 100;
    });

    constructor(private http: HttpClient) {}

    ngOnInit(): void {
        this.fetchPortfolio();
        this.fetchMetrics();
    }

    fetchPortfolio(): void {
        const userId = 'test_user';

        // this.http.get<any>(`${this.apiUrl}/api/portfolio/${userId}`).subscribe({
        //     next: (data) => {
        //         console.log('Recieved portfolio data:', data);
        //     this.portfolioValue.set(data.currentValue);
        //     this.previousCloseValue.set(data.previousClose);
        // },
        // error: (err) => {
        //     console.error('Failed to fetch portfolio', err);
        // }})
    }

    fetchMetrics(): void {
        this.http.get<any>(`${this.apiUrl}/api/metrics/${this.ticker}`).subscribe({
            next: (data) => {
                console.log('Recieved metrics data:', data);
            this.marketCap.set(data.market_cap);
            this.peRatio.set(data.pe_ratio)
            this.volume.set(data.volume)
            this.dividendYield.set(data.dividend_yield)

            }
        })
    }
}