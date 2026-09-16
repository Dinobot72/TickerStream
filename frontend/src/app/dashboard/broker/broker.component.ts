import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';

import {
  BrokerAccount,
  BrokerPosition,
  BrokerService,
  BrokerStatus,
  MarketClock,
} from '../../services/broker.service';

@Component({
  selector: 'broker',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './broker.component.html',
  styleUrls: ['./broker.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BrokerComponent implements OnInit {
  private broker = inject(BrokerService);

  // --- State ---
  status = signal<BrokerStatus | null>(null);
  account = signal<BrokerAccount | null>(null);
  positions = signal<BrokerPosition[]>([]);
  clock = signal<MarketClock | null>(null);

  isLoadingStatus = signal(true);
  isLoadingAccount = signal(false);
  isSubmitting = signal(false);
  isSyncing = signal(false);

  error = signal<string | null>(null);
  success = signal<string | null>(null);

  // --- Paper link form ---
  paperApiKey = signal('');
  paperSecretKey = signal('');

  // --- Live link form ---
  showLiveForm = signal(false);
  liveApiKey = signal('');
  liveSecretKey = signal('');
  liveAcknowledged = signal(false);
  liveConfirmText = signal('');

  // --- Unlink confirmation ---
  showUnlinkConfirm = signal(false);

  // --- Derived ---
  isLinked = computed(() => !!this.status()?.linked);
  isLive = computed(() => this.status()?.mode === 'live');
  isEnabled = computed(() => !!this.status()?.is_enabled);

  /** Orders only reach Alpaca when a link exists AND routing is switched on. */
  isRouting = computed(() => this.isLinked() && this.isEnabled());

  encryptionMissing = computed(() => {
    const s = this.status();
    return !!s && !s.encryption_configured;
  });

  /**
   * Live can only be offered when the server-wide gate is open. Showing the form
   * otherwise would just produce a 403 after the user had typed real
   * credentials into it.
   */
  canOfferLive = computed(() => !!this.status()?.server_allows_live);

  /**
   * Typing the phrase is the last speed bump before real money. Paired with the
   * checkbox so neither a stray click nor autofill alone can arm it.
   */
  liveFormValid = computed(
    () =>
      this.liveApiKey().trim().length >= 8 &&
      this.liveSecretKey().trim().length >= 8 &&
      this.liveAcknowledged() &&
      this.liveConfirmText().trim().toUpperCase() === 'TRADE REAL MONEY',
  );

  paperFormValid = computed(
    () => this.paperApiKey().trim().length >= 8 && this.paperSecretKey().trim().length >= 8,
  );

  totalUnrealized = computed(() =>
    this.positions().reduce((sum, p) => sum + (p.unrealized_pl || 0), 0),
  );

  ngOnInit(): void {
    this.loadStatus();
  }

  // --- Loading --------------------------------------------------------------

  loadStatus(): void {
    this.isLoadingStatus.set(true);
    this.broker
      .refreshStatus()
      .pipe(finalize(() => this.isLoadingStatus.set(false)))
      .subscribe((status) => {
        this.status.set(status);
        if (status?.linked && status.is_enabled) {
          this.loadAccountDetails();
        }
      });
  }

  loadAccountDetails(): void {
    this.isLoadingAccount.set(true);

    this.broker.getAccount().subscribe({
      next: (account) => {
        this.account.set(account);
        this.isLoadingAccount.set(false);
      },
      error: (err: Error) => {
        // A failure here means the link is unusable (closed gate, rotated
        // encryption key). Surface it rather than showing a blank panel.
        this.error.set(err.message);
        this.isLoadingAccount.set(false);
      },
    });

    this.broker.getPositions().subscribe({
      next: (positions) => this.positions.set(positions),
      error: () => this.positions.set([]),
    });

    this.broker.getClock().subscribe({
      next: (clock) => this.clock.set(clock),
      error: () => this.clock.set(null),
    });
  }

  // --- Linking --------------------------------------------------------------

  linkPaper(): void {
    if (!this.paperFormValid() || this.isSubmitting()) {
      return;
    }
    this.clearMessages();
    this.isSubmitting.set(true);

    this.broker
      .linkPaper(this.paperApiKey().trim(), this.paperSecretKey().trim())
      .pipe(finalize(() => this.isSubmitting.set(false)))
      .subscribe({
        next: () => {
          // Clear the inputs immediately — no reason to leave credentials
          // sitting in the DOM after they have been stored.
          this.paperApiKey.set('');
          this.paperSecretKey.set('');
          this.flashSuccess('Paper account linked. Orders will now route to Alpaca.');
          this.loadStatus();
        },
        error: (err: Error) => this.error.set(err.message),
      });
  }

  linkLive(): void {
    if (!this.liveFormValid() || this.isSubmitting()) {
      return;
    }
    this.clearMessages();
    this.isSubmitting.set(true);

    this.broker
      .linkLive(this.liveApiKey().trim(), this.liveSecretKey().trim())
      .pipe(finalize(() => this.isSubmitting.set(false)))
      .subscribe({
        next: () => {
          this.resetLiveForm();
          this.flashSuccess('Live account linked. Orders now use real money.');
          this.loadStatus();
        },
        error: (err: Error) => this.error.set(err.message),
      });
  }

  toggleLiveForm(): void {
    this.showLiveForm.update((v) => !v);
    if (!this.showLiveForm()) {
      this.resetLiveForm();
    }
  }

  private resetLiveForm(): void {
    this.liveApiKey.set('');
    this.liveSecretKey.set('');
    this.liveAcknowledged.set(false);
    this.liveConfirmText.set('');
    this.showLiveForm.set(false);
  }

  // --- Routing control ------------------------------------------------------

  toggleRouting(): void {
    const next = !this.isEnabled();
    this.clearMessages();

    this.broker.setEnabled(next).subscribe({
      next: () => {
        this.flashSuccess(
          next
            ? 'Broker routing resumed. Orders go to Alpaca.'
            : 'Broker routing paused. Orders will be simulated locally.',
        );
        this.loadStatus();
      },
      error: (err: Error) => this.error.set(err.message),
    });
  }

  confirmUnlink(): void {
    this.showUnlinkConfirm.set(true);
  }

  cancelUnlink(): void {
    this.showUnlinkConfirm.set(false);
  }

  unlink(): void {
    this.clearMessages();
    this.showUnlinkConfirm.set(false);

    this.broker.unlink().subscribe({
      next: () => {
        this.account.set(null);
        this.positions.set([]);
        this.clock.set(null);
        this.flashSuccess('Broker unlinked. Your trade history has been kept.');
        this.loadStatus();
      },
      error: (err: Error) => this.error.set(err.message),
    });
  }

  // --- Actions --------------------------------------------------------------

  syncNow(): void {
    this.clearMessages();
    this.isSyncing.set(true);

    this.broker
      .sync()
      .pipe(finalize(() => this.isSyncing.set(false)))
      .subscribe({
        next: (result) => {
          this.flashSuccess(
            `Synced. Cash ${this.money(result.cash)}, ${result.positions} position(s).`,
          );
          this.loadAccountDetails();
        },
        error: (err: Error) => this.error.set(err.message),
      });
  }

  reconcileNow(): void {
    this.clearMessages();

    this.broker.reconcile().subscribe({
      next: (result) => {
        this.flashSuccess(
          result.updated > 0
            ? `Updated ${result.updated} of ${result.checked} working order(s).`
            : 'No working orders to update.',
        );
        this.loadAccountDetails();
      },
      error: (err: Error) => this.error.set(err.message),
    });
  }

  // --- Formatting -----------------------------------------------------------

  money(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }
    return value.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
  }

  formatDate(value: string | null | undefined): string {
    if (!value) {
      return 'Never';
    }
    const parsed = new Date(value);
    return isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
  }

  private clearMessages(): void {
    this.error.set(null);
    this.success.set(null);
  }

  private flashSuccess(message: string): void {
    this.success.set(message);
    setTimeout(() => this.success.set(null), 4000);
  }
}
