import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, signal, OnInit, Injectable } from '@angular/core'
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
    providers:[HttpClient],
    templateUrl: './main-content.component.html',
    styleUrls: ['./main-content.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush,

})
export class MainContentComponent implements OnInit {

    private apiUrl = 'http://localhost:8000'; 

    public portfolioValue = signal(0)
    public previousCloseValue = signal(0)

    portfolioPercentage = computed(() => {
        const target = 10000;
        return Math.floor((this.portfolioValue() / target) * 100);
    });
    portfolioProgress = computed(() => {
        const circumference = 251.2;
        return circumference - (circumference * this.portfolioPercentage()) / 100;
    });

    constructor(private http: HttpClient) {}

    ngOnInit(): void {
        this.fetchPortfolio()
    }

    fetchPortfolio(): void {
        const userId = 'test_user';

        this.http.get<any>(`${this.apiUrl}/api/portfolio/${userId}`).subscribe({
            next: (data) => {
                console.log('Recieved portfolio data:', data)
            this.portfolioValue.set(data.currentValue);
            this.previousCloseValue.set(data.previousClose);
        },
        error: (err) => {
            console.error('Failed to fetch portfolio', err);
        }})
    }
}