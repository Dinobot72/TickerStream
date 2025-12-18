import { ComponentFixture, TestBed, fakeAsync, tick, flush } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { PLATFORM_ID, signal } from '@angular/core';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

import { PositionsComponent } from './positions.component';
import { AuthService } from '../../auth.service';

// Redefine interfaces for test scope as they are not exported from the component
interface TestApiHolding {
  ticker: string;
  quantity: number;
  purchase_price: number;
}

interface TestStockPrice {
  latestPrice?: number;
}

// Mock AuthService to control the currentUserId signal
class MockAuthService {
    currentUserId = signal<string | null>(null);
}

describe('PositionsComponent', () => {
    let component: PositionsComponent;
    let fixture: ComponentFixture<PositionsComponent>;
    let httpMock: HttpTestingController;
    let authService: MockAuthService;
    const apiUrl = '/api';
    const testUserId = 'user-pos-123';

    beforeEach(async () => {
        await TestBed.configureTestingModule({
            imports: [
                PositionsComponent, // It's standalone
                HttpClientTestingModule,
                NoopAnimationsModule, // For MatProgressSpinnerModule
            ],
            providers: [
                { provide: AuthService, useClass: MockAuthService },
                { provide: PLATFORM_ID, useValue: 'browser' }, // Default to browser for most tests
            ],
        }).compileComponents();

        fixture = TestBed.createComponent(PositionsComponent);
        component = fixture.componentInstance;
        httpMock = TestBed.inject(HttpTestingController);
        authService = TestBed.inject(AuthService) as unknown as MockAuthService;

        // Set a default user ID for most tests
        authService.currentUserId.set(testUserId);
    });

    afterEach(() => {
        httpMock.verify(); // Ensure no outstanding HTTP requests
    });

    it('should create', () => {
        fixture.detectChanges(); // ngOnInit
        expect(component).toBeTruthy();
        // Expect initial call to fetch holdings and flush it
        httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`).flush([]);
    });

    describe('Initialization (ngOnInit)', () => {
        it('should not fetch data on the server', () => {
            TestBed.overrideProvider(PLATFORM_ID, { useValue: 'server' });
            const serverFixture = TestBed.createComponent(PositionsComponent);
            const serverComponent = serverFixture.componentInstance;
            const fetchSpy = spyOn(serverComponent, 'fetchHoldingsAndPrices');
            
            serverFixture.detectChanges(); // ngOnInit
            
            expect(fetchSpy).not.toHaveBeenCalled();
            expect(serverComponent.isLoading()).toBe(false);
        });

        it('should call fetchHoldingsAndPrices on the browser', () => {
            const fetchSpy = spyOn(component, 'fetchHoldingsAndPrices');
            fixture.detectChanges(); // ngOnInit
            expect(fetchSpy).toHaveBeenCalledWith();
        });

        it('should set up a timer to refresh data every 30 seconds', fakeAsync(() => {
            const fetchSpy = spyOn(component, 'fetchHoldingsAndPrices').and.callThrough();
            
            fixture.detectChanges(); // ngOnInit, initial call
            httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`).flush([]);
            expect(fetchSpy).toHaveBeenCalledTimes(1);

            tick(29999);
            expect(fetchSpy).toHaveBeenCalledTimes(1);

            tick(1); // 30000ms
            httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`).flush([]);
            expect(fetchSpy).toHaveBeenCalledTimes(2);
            expect(fetchSpy).toHaveBeenCalledWith(false); // Should refresh without loading indicator

            component.ngOnDestroy(); // Clean up timer
            flush();
        }));
    });

    describe('fetchHoldingsAndPrices', () => {
        it('should not fetch if user is not logged in', () => {
            authService.currentUserId.set(null);
            component.fetchHoldingsAndPrices();
            expect(component.error()).toBe('User not logged in.');
            expect(component.isLoading()).toBe(false);
        });

        it('should set isLoading to true and then false on successful fetch', () => {
            component.fetchHoldingsAndPrices();
            expect(component.isLoading()).toBe(true);

            const req = httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`);
            req.flush([]); // Empty holdings

            expect(component.positions().length).toBe(0);
            expect(component.isLoading()).toBe(false);
        });

        it('should fetch holdings and prices, then calculate display values', () => {
            const mockApiHoldings: TestApiHolding[] = [
                { ticker: 'AAPL', quantity: 10, purchase_price: 150 },
                { ticker: 'GOOG', quantity: 5, purchase_price: 2500 },
            ];
            const mockAaplPrice: TestStockPrice = { latestPrice: 170 };
            const mockGoogPrice: TestStockPrice = { latestPrice: 2700 };

            component.fetchHoldingsAndPrices();

            httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`).flush(mockApiHoldings);
            httpMock.expectOne(`${apiUrl}/stock/AAPL`).flush(mockAaplPrice);
            httpMock.expectOne(`${apiUrl}/stock/GOOG`).flush(mockGoogPrice);

            const holdings = component.positions();
            expect(holdings.length).toBe(2);
            
            const aaplHolding = holdings.find(h => h.ticker === 'AAPL')!;
            expect(aaplHolding.current_price).toBe(170);
            expect(aaplHolding.total_value).toBe(1700); // 10 * 170
            expect(aaplHolding.total_pl).toBe(200); // (10 * 170) - (10 * 150)
            expect(aaplHolding.total_pl_pct).toBeCloseTo(200 / 1500);

            const googHolding = holdings.find(h => h.ticker === 'GOOG')!;
            expect(googHolding.current_price).toBe(2700);
            expect(googHolding.total_value).toBe(13500); // 5 * 2700
            expect(googHolding.total_pl).toBe(1000); // (5 * 2700) - (5 * 2500)
            expect(googHolding.total_pl_pct).toBeCloseTo(1000 / 12500);

            expect(component.isLoading()).toBe(false);
            expect(component.error()).toBeNull();
        });

        it('should handle API error when fetching holdings', () => {
            component.fetchHoldingsAndPrices();
            httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`).flush('Error', { status: 500, statusText: 'Server Error' });

            expect(component.error()).toBe('Failed to load positions. Please try again.');
            expect(component.positions().length).toBe(0);
            expect(component.isLoading()).toBe(false);
        });

        it('should handle an error when fetching a single stock price', () => {
            const mockApiHoldings: TestApiHolding[] = [{ ticker: 'BAD', quantity: 2, purchase_price: 50 }];
            component.fetchHoldingsAndPrices();

            httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`).flush(mockApiHoldings);
            httpMock.expectOne(`${apiUrl}/stock/BAD`).flush({}, { status: 404, statusText: 'Not Found' });

            const holdings = component.positions();
            expect(holdings.length).toBe(1);
            const badHolding = holdings[0];
            // Per component logic, a failed price fetch results in a price of 0
            expect(badHolding.current_price).toBe(0);
            expect(badHolding.total_value).toBe(0); // 2 * 0
            expect(badHolding.total_pl).toBe(-100); // (2 * 0) - (2 * 50)
            expect(badHolding.total_pl_pct).toBe(-1); // -100 / 100
        });
    });

    it('should unsubscribe from refresh timer on destroy', () => {
        const sub = { unsubscribe: jasmine.createSpy('unsubscribe') };
        (component as any).refreshSubscription = sub;
        component.ngOnDestroy();
        expect(sub.unsubscribe).toHaveBeenCalled();
    });
});
