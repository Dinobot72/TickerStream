import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';

import { BrokerService, BrokerStatus } from './broker.service';

const UNLINKED: BrokerStatus = {
  linked: false,
  mode: null,
  is_enabled: false,
  encryption_configured: true,
  server_allows_live: false,
  server_allows_live_bot: false,
};

const LINKED_PAPER: BrokerStatus = {
  linked: true,
  provider: 'alpaca',
  mode: 'paper',
  is_enabled: true,
  broker_account_id: 'PA12345',
  linked_at: '2026-01-01T00:00:00Z',
  live_confirmed: false,
  last_sync_at: null,
  encryption_configured: true,
  server_allows_live: false,
  server_allows_live_bot: false,
};

describe('BrokerService', () => {
  let service: BrokerService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [BrokerService, provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(BrokerService);
    httpMock = TestBed.inject(HttpTestingController);

    // The constructor kicks off an initial status fetch in the browser.
    const initial = httpMock.match('/api/broker/status');
    initial.forEach((req) => req.flush(UNLINKED));
  });

  afterEach(() => httpMock.verify());

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('publishes status to both the observable and the signal', () => {
    service.refreshStatus().subscribe();
    httpMock.expectOne('/api/broker/status').flush(LINKED_PAPER);

    expect(service.currentStatus?.mode).toBe('paper');
    expect(service.status()?.mode).toBe('paper');
  });

  describe('isRouting', () => {
    it('is false when nothing is linked', () => {
      expect(service.isRouting).toBeFalse();
    });

    it('is true for an enabled link', () => {
      service.refreshStatus().subscribe();
      httpMock.expectOne('/api/broker/status').flush(LINKED_PAPER);
      expect(service.isRouting).toBeTrue();
    });

    it('is false when a link exists but routing is paused', () => {
      service.refreshStatus().subscribe();
      httpMock
        .expectOne('/api/broker/status')
        .flush({ ...LINKED_PAPER, is_enabled: false });
      expect(service.isRouting).toBeFalse();
    });
  });

  it('sends paper credentials to the paper endpoint', () => {
    service.linkPaper('PKTESTKEY', 'TESTSECRET').subscribe();

    const req = httpMock.expectOne('/api/broker/link');
    expect(req.request.method).toBe('POST');
    expect(req.request.body.api_key).toBe('PKTESTKEY');
    req.flush(LINKED_PAPER);

    httpMock.expectOne('/api/broker/status').flush(LINKED_PAPER);
  });

  it('always sends the acknowledgement flag when linking live', () => {
    service.linkLive('LIVEKEY', 'LIVESECRET').subscribe();

    const req = httpMock.expectOne('/api/broker/link/live');
    expect(req.request.body.acknowledge_real_money).toBeTrue();
    req.flush({ ...LINKED_PAPER, mode: 'live', live_confirmed: true });

    httpMock.expectOne('/api/broker/status').flush(LINKED_PAPER);
  });

  it('surfaces the backend detail message verbatim', (done) => {
    // The backend explains which live gate is closed; a generic message would
    // leave the user with nothing actionable.
    const detail = 'Live trading is disabled server-wide (ALLOW_LIVE_TRADING is off).';

    service.linkLive('LIVEKEY', 'LIVESECRET').subscribe({
      error: (err: Error) => {
        expect(err.message).toBe(detail);
        done();
      },
    });

    httpMock
      .expectOne('/api/broker/link/live')
      .flush({ detail }, { status: 403, statusText: 'Forbidden' });
  });

  it('reports an unreachable server distinctly', (done) => {
    service.sync().subscribe({
      error: (err: Error) => {
        expect(err.message).toContain('Could not reach the server');
        done();
      },
    });

    httpMock
      .expectOne('/api/broker/sync')
      .error(new ProgressEvent('error'), { status: 0, statusText: 'Unknown Error' });
  });

  it('unlinks via DELETE', () => {
    service.unlink().subscribe();

    const req = httpMock.expectOne('/api/broker/unlink');
    expect(req.request.method).toBe('DELETE');
    req.flush({ message: 'Broker account unlinked.', linked: false });

    httpMock.expectOne('/api/broker/status').flush(UNLINKED);
  });
});
