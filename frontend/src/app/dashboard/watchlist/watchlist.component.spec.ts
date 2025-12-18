import { ComponentFixture, TestBed, fakeAsync, tick, flush } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

import { WatchlistComponent } from './watchlist.component';
import { AuthService } from '../../auth.service';

// Redefine interfaces for test scope as they are not exported from the component
interface TestWatchlistApiItem {
    ticker: string;
    added_at: string;
}

interface TestStockPrice {
    latestPrice?: number;
}

interface TestStockMetric {
     market_cap: string;
     pe_ratio: string;
     dividend_yield: number;
     volume: string;
     shortName?: string;
}

// Mock AuthService
class MockAuthService {
    currentUserId = signal<string | null>(null);
}

describe('WatchlistComponent', () => {
    let component: WatchlistComponent;
    let fixture: ComponentFixture<WatchlistComponent>;
    let httpMock: HttpTestingController;
    let authService: MockAuthService;
    const apiUrl = '/api';
    const testUserId = 'user-123';

    beforeEach(async () => {
        await TestBed.configureTestingModule({
            imports: [
                WatchlistComponent, // It's standalone
                HttpClientTestingModule,
                FormsModule,
                NoopAnimationsModule,
            ],
            providers: [
                { provide: AuthService, useClass: MockAuthService },
                { provide: PLATFORM_ID, useValue: 'browser' }, // Default to browser for most tests
            ],
        }).compileComponents();

        fixture = TestBed.createComponent(WatchlistComponent);
        component = fixture.componentInstance;
        httpMock = TestBed.inject(HttpTestingController);
        authService = TestBed.inject(AuthService) as unknown as MockAuthService;

        // Set a default user ID for most tests
        authService.currentUserId.set(testUserId);
    });

    afterEach(() => {
        httpMock.verify();
    });

    it('should create', () => {
        fixture.detectChanges(); // ngOnInit
        expect(component).toBeTruthy();
        // Expect initial call to fetch watchlist
        const req = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`);
        req.flush([]); // Flush with empty array to complete the cycle
    });

    describe('Initialization (ngOnInit)', () => {
        it('should not fetch data on the server', () => {
            // Override PLATFORM_ID for this test
            TestBed.overrideProvider(PLATFORM_ID, { useValue: 'server' });
            const serverFixture = TestBed.createComponent(WatchlistComponent);
            const serverComponent = serverFixture.componentInstance;
            const fetchSpy = spyOn(serverComponent, 'fetchWatchlistAndDetails');
            
            serverFixture.detectChanges(); // ngOnInit
            
            expect(fetchSpy).not.toHaveBeenCalled();
            expect(serverComponent.isLoading()).toBe(false);
        });

        it('should call fetchWatchlistAndDetails on the browser', () => {
            const fetchSpy = spyOn(component, 'fetchWatchlistAndDetails');
            fixture.detectChanges(); // ngOnInit
            expect(fetchSpy).toHaveBeenCalledWith();
        });

        it('should set up a timer to refresh data every 60 seconds', fakeAsync(() => {
            const fetchSpy = spyOn(component, 'fetchWatchlistAndDetails').and.callThrough();
            
            fixture.detectChanges(); // ngOnInit, initial call
            httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`).flush([]);
            expect(fetchSpy).toHaveBeenCalledTimes(1);

            tick(59999);
            expect(fetchSpy).toHaveBeenCalledTimes(1);

            tick(1); // 60000ms
            httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`).flush([]);
            expect(fetchSpy).toHaveBeenCalledTimes(2);
            expect(fetchSpy).toHaveBeenCalledWith(false); // Should refresh without loading indicator

            component.ngOnDestroy(); // Clean up timer
            flush();
        }));
    });

    describe('fetchWatchlistAndDetails', () => {
        it('should not fetch if user is not logged in', () => {
            authService.currentUserId.set(null);
            component.fetchWatchlistAndDetails();
            // httpMock.verify() in afterEach will fail if any request is made
            expect(component.infoMessage()?.text).toBe('User not logged in.');
            expect(component.isLoading()).toBe(false);
        });

        it('should set isLoading to true and then false on successful fetch', () => {
            expect(component.isLoading()).toBe(true); // Initial state
            component.fetchWatchlistAndDetails();
            expect(component.isLoading()).toBe(true);

            const req = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`);
            req.flush([]); // Empty watchlist

            expect(component.watchlistItems().length).toBe(0);
            expect(component.isLoading()).toBe(false);
        });

        it('should fetch watchlist and details for each ticker', () => {
            const mockApiItems: TestWatchlistApiItem[] = [
                { ticker: 'AAPL', added_at: '2023-01-01' },
                { ticker: 'GOOG', added_at: '2023-01-02' },
            ];
            const mockAaplPrice: TestStockPrice = { latestPrice: 150 };
            const mockAaplMetrics: TestStockMetric = { shortName: 'Apple Inc.', volume: '100,000', market_cap: '2.5T', pe_ratio: '25', dividend_yield: 0.01 };
            const mockGoogPrice: TestStockPrice = { latestPrice: 2800 };
            const mockGoogMetrics: TestStockMetric = { shortName: 'Alphabet Inc.', volume: '50,000', market_cap: '2T', pe_ratio: '30', dividend_yield: 0 };

            component.fetchWatchlistAndDetails();

            const watchlistReq = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`);
            watchlistReq.flush(mockApiItems);

            httpMock.expectOne(`${apiUrl}/stock/AAPL`).flush(mockAaplPrice);
            httpMock.expectOne(`${apiUrl}/metrics/AAPL`).flush(mockAaplMetrics);
            httpMock.expectOne(`${apiUrl}/stock/GOOG`).flush(mockGoogPrice);
            httpMock.expectOne(`${apiUrl}/metrics/GOOG`).flush(mockGoogMetrics);

            const items = component.watchlistItems();
            expect(items.length).toBe(2);
            expect(items[0].ticker).toBe('AAPL');
            expect(items[0].name).toBe('Apple Inc.');
            expect(items[0].current_price).toBe(150);
            expect(items[0].volume).toBe(100000);
            expect(items[1].ticker).toBe('GOOG');
            expect(items[1].name).toBe('Alphabet Inc.');
            expect(items[1].current_price).toBe(2800);
            expect(items[1].volume).toBe(50000);

            expect(component.isLoading()).toBe(false);
        });

        it('should handle API error when fetching watchlist', () => {
            component.fetchWatchlistAndDetails();
            const req = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`);
            req.flush('Error', { status: 500, statusText: 'Server Error' });

            expect(component.infoMessage()?.text).toBe('Failed to load watchlist details.');
            expect(component.watchlistItems().length).toBe(0);
            expect(component.isLoading()).toBe(false);
        });
    });

    describe('addTicker', () => {
        beforeEach(() => {
            spyOn(component, 'fetchWatchlistAndDetails').and.stub();
            fixture.detectChanges();
        });

        it('should show error if ticker is already in watchlist', fakeAsync(() => {
            component.watchlistItems.set([{ ticker: 'AAPL', current_price: 1, change: 1, change_pct: 1, volume: 1 }]);
            component.newTicker.set('AAPL');
            component.addTicker();
            expect(component.infoMessage()?.text).toBe('AAPL is already in the watchlist.');
            tick(3000);
            expect(component.infoMessage()).toBeNull();
        }));

        it('should POST to add a new ticker and refresh list on success', fakeAsync(() => {
            const fetchSpy = (component.fetchWatchlistAndDetails as jasmine.Spy).and.callFake(() => {});
            
            component.newTicker.set('TSLA');
            component.addTicker();

            expect(component.isAdding()).toBe(true);

            const req = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`);
            expect(req.request.method).toBe('POST');
            expect(req.request.body).toEqual({ ticker: 'TSLA' });
            req.flush({ message: 'TSLA added successfully.' });

            expect(component.isAdding()).toBe(false);
            expect(component.infoMessage()?.text).toBe('TSLA added successfully.');
            expect(component.newTicker()).toBe('');
            expect(fetchSpy).toHaveBeenCalledWith(false);

            tick(3000);
            expect(component.infoMessage()).toBeNull();
        }));

        it('should handle error on adding a ticker', fakeAsync(() => {
            component.newTicker.set('BAD');
            component.addTicker();

            const req = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`);
            req.flush({ detail: 'Invalid ticker' }, { status: 400, statusText: 'Bad Request' });

            expect(component.isAdding()).toBe(false);
            expect(component.infoMessage()?.text).toBe('Invalid ticker');

            tick(3000);
            expect(component.infoMessage()).toBeNull();
        }));
    });

    describe('removeTicker', () => {
        beforeEach(() => {
            spyOn(component, 'fetchWatchlistAndDetails').and.stub();
            fixture.detectChanges();
        });

        it('should DELETE a ticker and refresh list on success', fakeAsync(() => {
            const fetchSpy = (component.fetchWatchlistAndDetails as jasmine.Spy).and.callFake(() => {});

            component.removeTicker('AAPL');

            const req = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}/AAPL`);
            expect(req.request.method).toBe('DELETE');
            req.flush({ message: 'AAPL removed.' });

            expect(component.infoMessage()?.text).toBe('AAPL removed.');
            expect(fetchSpy).toHaveBeenCalledWith(false);

            tick(3000);
            expect(component.infoMessage()).toBeNull();
        }));

        it('should handle error on removing a ticker', fakeAsync(() => {
            component.removeTicker('AAPL');

            const req = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}/AAPL`);
            req.flush({ detail: 'Ticker not found' }, { status: 404, statusText: 'Not Found' });

            expect(component.infoMessage()?.text).toBe('Ticker not found');

            tick(3000);
            expect(component.infoMessage()).toBeNull();
        }));
    });

    it('should unsubscribe from refresh timer on destroy', () => {
        const sub = { unsubscribe: jasmine.createSpy('unsubscribe') };
        (component as any).refreshSubscription = sub;
        component.ngOnDestroy();
        expect(sub.unsubscribe).toHaveBeenCalled();
    });
});
