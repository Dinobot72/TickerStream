import { ComponentFixture, TestBed, fakeAsync, tick, flush } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

import { WatchlistComponent } from './watchlist.component';
import { AuthService } from '../../auth.service';

// --- Interfaces & Mocks ---

interface TestWatchlistApiItem { ticker: string; added_at: string; }
interface TestStockPrice { latestPrice?: number; }
interface TestStockMetric { market_cap: string; pe_ratio: string; dividend_yield: number; volume: string; shortName?: string; }

class MockAuthService {
    currentUserId = signal<string | null>(null);
}

describe('WatchlistComponent', () => {
    let component: WatchlistComponent;
    let fixture: ComponentFixture<WatchlistComponent>;
    let httpMock: HttpTestingController;
    let authService: MockAuthService;
    const apiUrl= 'https://auth.ticker-stream.com/api';
    const testUserId = 'user-123';

    // Helper to configure TestBed per suite
    const configureTestBed = async (platform: 'browser' | 'server') => {
        await TestBed.configureTestingModule({
            imports: [
                WatchlistComponent,
                HttpClientTestingModule,
                FormsModule,
                NoopAnimationsModule,
            ],
            providers: [
                { provide: AuthService, useClass: MockAuthService },
                { provide: PLATFORM_ID, useValue: platform }, // Inject Platform Here
            ],
        }).compileComponents();

        fixture = TestBed.createComponent(WatchlistComponent);
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

        it('should create but NOT fetch data or start timers', () => {
            const fetchSpy = spyOn(component, 'fetchWatchlistAndDetails');
            
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

        it('should create and fetch initial watchlist', () => {
            fixture.detectChanges(); // ngOnInit
            expect(component).toBeTruthy();
            
            const req = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`);
            expect(req.request.method).toBe('GET');
            req.flush([]);
        });

        it('should set up a timer to refresh data every 60 seconds', fakeAsync(() => {
            // Spy on the method to track calls
            const fetchSpy = spyOn(component, 'fetchWatchlistAndDetails').and.callThrough();
            
            // 1. Initial Load
            fixture.detectChanges(); 
            httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`).flush([]);
            expect(fetchSpy).toHaveBeenCalledTimes(1);

            // 2. Fast forward 59.9s (should be no call yet)
            tick(59999);
            expect(fetchSpy).toHaveBeenCalledTimes(1);

            // 3. Fast forward past 60s (should trigger refresh)
            tick(1); 
            httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`).flush([]);
            expect(fetchSpy).toHaveBeenCalledTimes(2);
            expect(fetchSpy).toHaveBeenCalledWith(false); // Called with refresh=true logic (isLoading=false)

            // 4. Cleanup
            component.ngOnDestroy();
            flush();
        }));

        describe('fetchWatchlistAndDetails', () => {
            it('should not fetch if user is not logged in', () => {
                // Initialize component first to clear the auto-fetch from ngOnInit
                fixture.detectChanges();
                httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`).flush([]);

                // Now test the specific method logic
                authService.currentUserId.set(null);
                component.fetchWatchlistAndDetails();
                
                expect(component.infoMessage()?.text).toBe('User not logged in.');
                expect(component.isLoading()).toBe(false);
            });

            it('should fetch watchlist and details for each ticker', () => {
                // Clear init request
                fixture.detectChanges();
                httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`).flush([]);

                const mockApiItems: TestWatchlistApiItem[] = [
                    { ticker: 'AAPL', added_at: '2023-01-01' },
                    { ticker: 'GOOG', added_at: '2023-01-02' },
                ];
                
                // Trigger manual fetch
                component.fetchWatchlistAndDetails();

                const watchlistReq = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`);
                watchlistReq.flush(mockApiItems);

                httpMock.expectOne(`${apiUrl}/stock/AAPL`).flush({ latestPrice: 150 });
                httpMock.expectOne(`${apiUrl}/metrics/AAPL`).flush({ shortName: 'Apple Inc.', volume: '100k', market_cap: '2.5T', pe_ratio: '25', dividend_yield: 0.01 });
                httpMock.expectOne(`${apiUrl}/stock/GOOG`).flush({ latestPrice: 2800 });
                httpMock.expectOne(`${apiUrl}/metrics/GOOG`).flush({ shortName: 'Alphabet Inc.', volume: '50k', market_cap: '2T', pe_ratio: '30', dividend_yield: 0 });

                const items = component.watchlistItems();
                expect(items.length).toBe(2);
                expect(items[0].ticker).toBe('AAPL');
                expect(items[1].ticker).toBe('GOOG');
            });

            it('should handle API error when fetching watchlist', () => {
                fixture.detectChanges();
                httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`).flush([]);

                component.fetchWatchlistAndDetails();
                
                const req = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`);
                req.flush('Error', { status: 500, statusText: 'Server Error' });

                expect(component.infoMessage()?.text).toBe('Failed to load watchlist details.');
                expect(component.watchlistItems().length).toBe(0);
            });
        });

        describe('addTicker', () => {
            beforeEach(() => {
                // Initialize and clear startup request
                fixture.detectChanges();
                httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`).flush([]);
                
                // Spy to prevent further refreshes during these specific tests
                spyOn(component, 'fetchWatchlistAndDetails').and.stub();
            });

            it('should show error if ticker is already in watchlist', fakeAsync(() => {
                component.watchlistItems.set([{ ticker: 'AAPL' } as any]);
                component.newTicker.set('AAPL');
                
                component.addTicker();
                
                expect(component.infoMessage()?.text).toBe('AAPL is already in the watchlist.');
                tick(3000);
                expect(component.infoMessage()).toBeNull();
            }));

            it('should POST to add a new ticker and refresh list on success', fakeAsync(() => {
                const fetchSpy = (component.fetchWatchlistAndDetails as jasmine.Spy);
                
                component.newTicker.set('TSLA');
                component.addTicker();

                expect(component.isAdding()).toBe(true);

                const req = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`);
                expect(req.request.method).toBe('POST');
                req.flush({ message: 'TSLA added successfully.' });

                expect(component.isAdding()).toBe(false);
                expect(component.infoMessage()?.text).toBe('TSLA added successfully.');
                expect(fetchSpy).toHaveBeenCalledWith(false); // Expect refresh

                tick(3000);
                expect(component.infoMessage()).toBeNull();
            }));
        });

        describe('removeTicker', () => {
            beforeEach(() => {
                fixture.detectChanges();
                httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`).flush([]);
                spyOn(component, 'fetchWatchlistAndDetails').and.stub();
            });

            it('should DELETE a ticker and refresh list on success', fakeAsync(() => {
                const fetchSpy = (component.fetchWatchlistAndDetails as jasmine.Spy);

                component.removeTicker('AAPL');

                const req = httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}/AAPL`);
                expect(req.request.method).toBe('DELETE');
                req.flush({ message: 'AAPL removed.' });

                expect(component.infoMessage()?.text).toBe('AAPL removed.');
                expect(fetchSpy).toHaveBeenCalledWith(false);

                tick(3000);
                expect(component.infoMessage()).toBeNull();
            }));
        });

        it('should unsubscribe from refresh timer on destroy', () => {
            fixture.detectChanges();
            httpMock.expectOne(`${apiUrl}/watchlist/${testUserId}`).flush([]);

            const sub = { unsubscribe: jasmine.createSpy('unsubscribe') };
            (component as any).refreshSubscription = sub;
            
            component.ngOnDestroy();
            expect(sub.unsubscribe).toHaveBeenCalled();
        });
    });
});