import { ChangeDetectionStrategy, Component, signal } from "@angular/core";
import { CommonModule } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { RouterModule } from "@angular/router";

interface WatchlistItem {
    ticker: string;
    name?: string;
    current_price: number;
    change: number;
    change_pct: number;
    volume: number;
}

@Component({
    selector: 'watchlist',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        RouterModule
    ],
    templateUrl: './watchlist.component.html',
    styleUrls: ['./watchlist.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush,
})

export class WatchlistComponent {
    watchlistItems = signal<WatchlistItem[]>([
        { ticker: 'AAPL', name: 'Apple Inc.', current_price: 175.00, change: 1.50, change_pct: 0.86, volume: 50000000 },
        { ticker: 'GOOGL', name: 'Alphabet Inc.', current_price: 2800.00, change: -10.00, change_pct: -0.36, volume: 1500000 },
        { ticker: 'TSLA', name: 'Tesla, Inc.', current_price: 700.00, change: 15.00, change_pct: 2.19, volume: 25000000 },
    ]);
    newTicker = signal('');
    infoMessage = signal<{type: 'error' | 'success', text: string} | null>(null);

    addTicker(): void {
        const tickerToAdd = this.newTicker().trim().toUpperCase();
        if (!tickerToAdd) {
            this.infoMessage.set({type: 'error', text: 'Please enter a ticker symbol.'});
            return;
        }

        if (this.watchlistItems().some(item => item.ticker === tickerToAdd)) {
            this.infoMessage.set({type: 'error', text: `${tickerToAdd} already in watchlist.`});
            return;
        }

        this.watchlistItems.update(items => [...items, { 
            ticker: tickerToAdd, 
            current_price: 0, 
            change: 0, 
            change_pct: 0, 
            volume: 0 ,
        }]);
        this.newTicker.set('');
        this.infoMessage.set({type: 'success', text: `${tickerToAdd} added to watchlist.`});
    }

    removeTicker(tickerToRemove: string): void {
        this.watchlistItems.update(items => items.filter(item => item.ticker !== tickerToRemove));
        this.infoMessage.set({type: 'success', text: `${tickerToRemove} removed from watchlist.`})
    }
}