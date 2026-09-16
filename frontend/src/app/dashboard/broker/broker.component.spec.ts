import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { BrokerComponent } from './broker.component';
import { BrokerStatus } from '../../services/broker.service';

const UNLINKED: BrokerStatus = {
  linked: false,
  mode: null,
  is_enabled: false,
  encryption_configured: true,
  server_allows_live: false,
  server_allows_live_bot: false,
};

const LINKED_PAPER: BrokerStatus = {
  ...UNLINKED,
  linked: true,
  provider: 'alpaca',
  mode: 'paper',
  is_enabled: true,
  broker_account_id: 'PA12345',
};

describe('BrokerComponent', () => {
  let fixture: ComponentFixture<BrokerComponent>;
  let component: BrokerComponent;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [BrokerComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(BrokerComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.match('/api/broker/status').forEach((r) => r.flush(UNLINKED));
    httpMock.match(() => true).forEach((r) => r.flush({}));
    httpMock.verify();
  });

  /** Settles the initial status fetch(es) with the given payload. */
  function initialise(status: BrokerStatus): void {
    fixture.detectChanges();
    httpMock.match('/api/broker/status').forEach((r) => r.flush(status));
    fixture.detectChanges();
  }

  it('should create', () => {
    initialise(UNLINKED);
    expect(component).toBeTruthy();
  });

  describe('execution mode', () => {
    it('reports simulated when nothing is linked', () => {
      initialise(UNLINKED);
      expect(component.isRouting()).toBeFalse();
      expect(fixture.nativeElement.textContent).toContain('SIMULATED');
    });

    it('reports paper for an enabled paper link', () => {
      initialise(LINKED_PAPER);
      expect(component.isRouting()).toBeTrue();
      expect(component.isLive()).toBeFalse();
    });

    it('reports simulated when a link exists but routing is paused', () => {
      initialise({ ...LINKED_PAPER, is_enabled: false });
      expect(component.isLinked()).toBeTrue();
      expect(component.isRouting()).toBeFalse();
    });
  });

  describe('live trading gate', () => {
    it('does not offer live when the server gate is closed', () => {
      initialise(LINKED_PAPER);
      expect(component.canOfferLive()).toBeFalse();
    });

    it('offers live when the server gate is open', () => {
      initialise({ ...LINKED_PAPER, server_allows_live: true });
      expect(component.canOfferLive()).toBeTrue();
    });
  });

  describe('live form validation', () => {
    beforeEach(() => initialise({ ...LINKED_PAPER, server_allows_live: true }));

    it('is invalid until every confirmation is satisfied', () => {
      component.liveApiKey.set('LIVEKEY123');
      component.liveSecretKey.set('LIVESECRET456');
      expect(component.liveFormValid()).toBeFalse();

      component.liveAcknowledged.set(true);
      expect(component.liveFormValid()).toBeFalse();

      component.liveConfirmText.set('TRADE REAL MONEY');
      expect(component.liveFormValid()).toBeTrue();
    });

    it('rejects a wrong confirmation phrase', () => {
      component.liveApiKey.set('LIVEKEY123');
      component.liveSecretKey.set('LIVESECRET456');
      component.liveAcknowledged.set(true);
      component.liveConfirmText.set('yes');
      expect(component.liveFormValid()).toBeFalse();
    });

    it('accepts the phrase case-insensitively', () => {
      component.liveApiKey.set('LIVEKEY123');
      component.liveSecretKey.set('LIVESECRET456');
      component.liveAcknowledged.set(true);
      component.liveConfirmText.set('trade real money');
      expect(component.liveFormValid()).toBeTrue();
    });
  });

  describe('paper form validation', () => {
    beforeEach(() => initialise(UNLINKED));

    it('rejects short or empty keys', () => {
      component.paperApiKey.set('short');
      component.paperSecretKey.set('alsoshort');
      expect(component.paperFormValid()).toBeFalse();
    });

    it('accepts a plausible key pair', () => {
      component.paperApiKey.set('PKTESTKEY123');
      component.paperSecretKey.set('TESTSECRET456');
      expect(component.paperFormValid()).toBeTrue();
    });
  });

  describe('encryption warning', () => {
    it('blocks linking when the server has no encryption key', () => {
      initialise({ ...UNLINKED, encryption_configured: false });
      expect(component.encryptionMissing()).toBeTrue();
      expect(fixture.nativeElement.textContent).toContain('BROKER_ENCRYPTION_KEY');
    });
  });

  describe('formatting', () => {
    beforeEach(() => initialise(UNLINKED));

    it('renders currency', () => {
      expect(component.money(1234.5)).toBe('$1,234.50');
    });

    it('renders missing values as a dash', () => {
      expect(component.money(null)).toBe('—');
    });

    it('renders a missing timestamp as Never', () => {
      expect(component.formatDate(null)).toBe('Never');
    });
  });
});
