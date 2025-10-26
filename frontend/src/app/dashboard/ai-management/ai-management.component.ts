import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

interface Activity {
    action: 'BUY' | 'SELL';
    ticker: string;
    quantity: number;
    price: number;
    timestamp: string;
    is_bot_trade: true;
}

@Component({
  selector: 'ai-management',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './ai-management.component.html',
  styleUrls: ['./ai-management.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiManagementComponent {

  // --- Bot Status ---
  isBotActive = signal(true);
  botStatusMessage = signal('Actively monitoring market...');
  lastActionTime = signal(new Date(Date.now() - 5 * 60 * 1000).toISOString()); // 5 mins ago

  // --- Bot Activity Log ---
  botActivityLog = signal<Activity[]>([
     { action: 'SELL', ticker: 'TSLA', quantity: 2, price: 250.00, is_bot_trade: true, timestamp: '2025-10-24T09:05:00Z' },
     { action: 'BUY', ticker: 'NVDA', quantity: 1, price: 900.00, is_bot_trade: true, timestamp: '2025-10-23T11:45:00Z' },
  ]);
  isLoadingActivity = signal(false);
  activityError = signal<string | null>(null);

  // --- Bot Performance (Example Signals) ---
  botTotalPL = signal(1250.75);
  botWinRate = signal(65);
  botTradesCount = signal(50);

  // --- Configuration (Placeholders) ---
  riskLevel = signal<'Low' | 'Medium' | 'High'>('Medium');
  allowedTickers = signal('AAPL, MSFT, GOOGL');


  toggleBotStatus(): void {
    this.isBotActive.update(active => !active);
    this.botStatusMessage.set(this.isBotActive() ? 'Starting bot...' : 'Stopping bot...');
    setTimeout(() => {
        this.botStatusMessage.set(this.isBotActive() ? 'Actively monitoring market...' : 'Bot is inactive.');
    }, 1500);
  }

}

