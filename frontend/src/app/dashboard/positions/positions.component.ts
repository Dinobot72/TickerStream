import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router'; // Import RouterModule for routerLink

// Define interface for Holding data
interface Holding {
    ticker: string;
    quantity: number;
    purchase_price: number;
    // Placeholder for calculated fields
    current_price: number;
    total_value: number;
    total_pl: number;
    total_pl_pct: number;
}

@Component({
  selector: 'app-positions',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './positions.component.html',
  styleUrls: ['./positions.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PositionsComponent {
  
  // Placeholder data
  holdings = signal<Holding[]>([
    { ticker: 'AAPL', quantity: 10, purchase_price: 150.00, current_price: 175.00, total_value: 1750.00, total_pl: 250.00, total_pl_pct: 16.67 },
    { ticker: 'MSFT', quantity: 5, purchase_price: 300.00, current_price: 320.00, total_value: 1600.00, total_pl: 100.00, total_pl_pct: 6.67 },
    { ticker: 'GOOGL', quantity: 2, purchase_price: 2800.00, current_price: 2750.00, total_value: 5500.00, total_pl: -100.00, total_pl_pct: -1.79 },
  ]);
  
  // Signals for loading and error states (can be toggled for testing)
  isLoading = signal(false);
  error = signal<string | null>(null);

  // Example of how you could test the error state:
  // error = signal<string | null>('Failed to fetch holdings. Please try again.');
  
  // Example of how you could test the empty state:
  // holdings = signal<Holding[]>([]);
}