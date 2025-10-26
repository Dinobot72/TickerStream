import { ChangeDetectionStrategy, Component, signal, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router'; // To read query params

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

  tradeAction = signal<'BUY' | 'SELL'>('BUY');
  ticker = signal('');
  quantity = signal<number | null>(null);
  orderType = signal<'MARKET' | 'LIMIT'>('MARKET');
  limitPrice = signal<number | null>(null);
  
  isSubmitting = signal(false);
  errorMessage = signal<string | null>(null);
  successMessage = signal<string | null>(null);

  // Placeholder for current price
  currentPrice = signal(123.45); // Static placeholder

  ngOnInit(): void {
    // Check for ticker in query params
    this.route.queryParams.subscribe(params => {
        if (params['ticker']) {
            this.ticker.set(params['ticker']);
            // In a real app, you'd fetch the price for this ticker
            // this.fetchCurrentPrice(); 
        }
    });
  }

  submitTrade(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);

    // --- Basic Validations ---
    if (!this.ticker().trim()) {
      this.errorMessage.set('Please enter a ticker symbol.');
      return;
    }
    if (!this.quantity() || this.quantity()! <= 0) {
      this.errorMessage.set('Please enter a valid quantity.');
      return;
    }
     if (this.orderType() === 'LIMIT' && (!this.limitPrice() || this.limitPrice()! <= 0)) {
        this.errorMessage.set('Please enter a valid limit price.');
        return;
    }

    this.isSubmitting.set(true);

    // Simulate trade execution
    setTimeout(() => {
        this.successMessage.set(`Trade submitted successfully: ${this.tradeAction()} ${this.quantity()} ${this.ticker().toUpperCase()}`);
        this.isSubmitting.set(false);
        
        // Reset form
        this.ticker.set('');
        this.quantity.set(null);
        this.limitPrice.set(null);
        
        // Clear success message after a few seconds
        setTimeout(() => this.successMessage.set(null), 4000);
    }, 1500);
  }
}

