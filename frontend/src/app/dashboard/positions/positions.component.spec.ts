import { ComponentFixture, TestBed, fakeAsync, tick, flush } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { PLATFORM_ID, signal } from '@angular/core';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

import { PositionsComponent } from './positions.component';
import { AuthService } from '../../auth.service';
import { provideRouter } from '@angular/router';

// --- Interfaces & Mocks ---

interface TestApiHolding {
  ticker: string;
  quantity: number;
  purchase_price: number;
}

interface TestStockPrice {
  latestPrice?: number;
}

class MockAuthService {
  currentUserId = signal<string | null>(null);
}

describe('PositionsComponent', () => {
  let component: PositionsComponent;
  let fixture: ComponentFixture<PositionsComponent>;
  let httpMock: HttpTestingController;
  let authService: MockAuthService;
  
  const apiUrl= 'https://auth.ticker-stream.com/api';
  const testUserId = 'user-pos-123';

  // --- Helper to Configure TestBed ---
  const configureTestBed = async (platform: 'browser' | 'server') => {
    await TestBed.configureTestingModule({
      imports: [
        PositionsComponent,
        HttpClientTestingModule,
        NoopAnimationsModule,
      ],
      providers: [
        provideRouter([]),
        { provide: AuthService, useClass: MockAuthService },
        { provide: PLATFORM_ID, useValue: platform }, // Inject specific platform
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(PositionsComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    authService = TestBed.inject(AuthService) as unknown as MockAuthService;

    // Set default user ID
    authService.currentUserId.set(testUserId);
  };

  afterEach(() => {
    httpMock.verify();
  });

  // =========================================================
  // 1. Server Environment Suite
  // =========================================================
  describe('Server Environment', () => {
    beforeEach(async () => {
      await configureTestBed('server');
    });

    it('should create but NOT fetch data', () => {
      const fetchSpy = spyOn(component, 'fetchHoldingsAndPrices');
      fixture.detectChanges(); // ngOnInit
      
      expect(component).toBeTruthy();
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(component.isLoading()).toBe(false);
    });
  });

  // =========================================================
  // 2. Browser Environment Suite
  // =========================================================
  describe('Browser Environment', () => {
    beforeEach(async () => {
      await configureTestBed('browser');
    });

    it('should create and fetch holdings immediately', () => {
      const fetchSpy = spyOn(component, 'fetchHoldingsAndPrices').and.callThrough();
      fixture.detectChanges(); // ngOnInit
      
      expect(fetchSpy).toHaveBeenCalled();
      // Flush the request triggered by ngOnInit
      httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`).flush([]);
    });

    it('should set up a timer to refresh data every 30 seconds', fakeAsync(() => {
        const fetchSpy = spyOn(component, 'fetchHoldingsAndPrices').and.callThrough();
        
        // 1. Init
        fixture.detectChanges(); 
        httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`).flush([]);
        expect(fetchSpy).toHaveBeenCalledTimes(1);

        // 2. Wait 29.9s (No call)
        tick(29999);
        expect(fetchSpy).toHaveBeenCalledTimes(1);

        // 3. Wait 30s (Trigger Refresh)
        tick(1);
        httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`).flush([]);
        expect(fetchSpy).toHaveBeenCalledTimes(2);
        expect(fetchSpy).toHaveBeenCalledWith(false); // Refresh mode

        // 4. Cleanup
        component.ngOnDestroy();
        flush();
    }));

    describe('fetchHoldingsAndPrices Logic', () => {
        // We initialize the component before these tests
        beforeEach(() => {
            fixture.detectChanges();
            // Flush the initial request so we can test specific scenarios cleanly
            httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`).flush([]);
        });

        it('should not fetch if user is not logged in', () => {
            authService.currentUserId.set(null);
            component.fetchHoldingsAndPrices();
            
            expect(component.error()).toBe('User not logged in.');
            expect(component.isLoading()).toBe(false);
        });

        it('should set isLoading and populate positions on success', () => {
            component.fetchHoldingsAndPrices();
            expect(component.isLoading()).toBe(true);

            const req = httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`);
            req.flush([]); 

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
            expect(aaplHolding.total_pl).toBe(200); // (1700 - 1500)
            
            expect(component.isLoading()).toBe(false);
            expect(component.error()).toBeNull();
        });

        it('should handle API error when fetching holdings', () => {
            component.fetchHoldingsAndPrices();
            const req = httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`);
            req.flush('Error', { status: 500, statusText: 'Server Error' });

            expect(component.error()).toBe('Failed to load positions. Please try again.');
            expect(component.positions().length).toBe(0);
            expect(component.isLoading()).toBe(false);
        });

        it('should handle error when fetching a single stock price', () => {
            const mockApiHoldings: TestApiHolding[] = [{ ticker: 'BAD', quantity: 2, purchase_price: 50 }];
            
            component.fetchHoldingsAndPrices();

            httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`).flush(mockApiHoldings);
            // Simulate 404 for price
            httpMock.expectOne(`${apiUrl}/stock/BAD`).flush({}, { status: 404, statusText: 'Not Found' });

            const holdings = component.positions();
            expect(holdings.length).toBe(1);
            const badHolding = holdings[0];
            
            // Logic dictates price defaults to 0 on error
            expect(badHolding.current_price).toBe(0);
            expect(badHolding.total_value).toBe(0); 
            expect(badHolding.total_pl).toBe(-100); // (0 - 100)
        });
    });

    it('should unsubscribe from refresh timer on destroy', () => {
        fixture.detectChanges();
        httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`).flush([]);

        const sub = { unsubscribe: jasmine.createSpy('unsubscribe') };
        (component as any).refreshSubscription = sub;
        
        component.ngOnDestroy();
        expect(sub.unsubscribe).toHaveBeenCalled();
    });
  });
});