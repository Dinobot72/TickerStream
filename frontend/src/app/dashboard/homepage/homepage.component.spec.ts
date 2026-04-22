import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { Component, ComponentRef, PLATFORM_ID, signal } from '@angular/core';
import { Router } from '@angular/router';
import { of, Subject } from 'rxjs';
import { Chart, registerables } from 'chart.js';

import { HomepageComponent } from './homepage.component';
import { AuthService } from '../../auth.service';
import { BotStatusService } from '../../services/bot-status.service';

// --- Mocks (Same as before) ---
class MockAuthService {
    currentUserId = signal<string | null>(null);
}

class MockBotStatusService {
    private statusSubject = new Subject<boolean>();
    botStatus$ = this.statusSubject.asObservable();
    setBotStatus(isActive: boolean) {
        this.statusSubject.next(isActive);
    }
}

interface Holding { ticker: string; quantity: number; purchase_price: number; }
interface Activity { action: string; ticker: string; quantity: number; price: number; is_bot_trade: boolean; timestamp?: string; }
interface MarketIndex { name: string, value: number, change: number, changePct: number;}
interface TrendingStock { ticker: string, price: number, changePct: number;}


describe('HomepageComponent', () => {
    // Shared variables
    let component: HomepageComponent;
    let fixture: ComponentFixture<HomepageComponent>;
    let httpMock: HttpTestingController;
    let authService: MockAuthService;
    let botStatusService: MockBotStatusService;
    let router: Router;

    const apiUrl= '/api';
    const testUserId = 'user-home-123';

    beforeAll(() => {
        Chart.register(...registerables);
    });

    // =========================================================
    // 1. Browser Environment Suite
    // (Moves the standard beforeEach here so it doesn't run for Server tests)
    // =========================================================
    describe('Browser Environment', () => {
        
        beforeEach(async () => {
            await TestBed.configureTestingModule({
                imports: [
                    HomepageComponent,
                    HttpClientTestingModule,
                    RouterTestingModule.withRoutes([{ path: 'login', component: class Dummy {} }]),
                ],
                providers: [
                    { provide: AuthService, useClass: MockAuthService },
                    { provide: BotStatusService, useClass: MockBotStatusService },
                    { provide: PLATFORM_ID, useValue: 'browser' },
                ],
            }).compileComponents();

            fixture = TestBed.createComponent(HomepageComponent);
            component = fixture.componentInstance;
            httpMock = TestBed.inject(HttpTestingController);
            authService = TestBed.inject(AuthService) as unknown as MockAuthService;
            botStatusService = TestBed.inject(BotStatusService) as unknown as MockBotStatusService;
            router = TestBed.inject(Router);

            authService.currentUserId.set(testUserId);
            spyOn(Chart.prototype, 'constructor' as any).and.callThrough();
        });

        afterEach(() => {
            httpMock.verify();
            component.ngOnDestroy();
        });

        it('should create', () => {
            spyOn(component, 'fetchUserData');
            spyOn(component, 'fetchPortfolio');
            spyOn(component, 'fetchMetrics');
            spyOn(component, 'fetchActivity');
            fixture.detectChanges();
            expect(component).toBeTruthy();
        });

        describe('Initialization', () => {
            it('should call fetch methods on ngOnInit in browser', () => {
                const fetchUserDataSpy = spyOn(component, 'fetchUserData');
                const fetchPortfolioSpy = spyOn(component, 'fetchPortfolio');
                const fetchMetricsSpy = spyOn(component, 'fetchMetrics');
                const fetchActivitySpy = spyOn(component, 'fetchActivity');

                fixture.detectChanges(); // ngOnInit

                expect(fetchUserDataSpy).toHaveBeenCalled();
                expect(fetchPortfolioSpy).toHaveBeenCalled();
                expect(fetchMetricsSpy).toHaveBeenCalled();
                expect(fetchActivitySpy).toHaveBeenCalled();
            });
        });

        describe('Data Fetching', () => {
            afterEach(() => {
                httpMock.verify();
            });

            it('should fetch user data and update signals', () => {
                const mockUser = { balance: 5000, first_name: 'Jane' };
                component.fetchUserData();
                const req = httpMock.expectOne(`${apiUrl}/user/${testUserId}`);
                expect(req.request.method).toBe('GET');
                req.flush(mockUser);
                expect(component.userBalance()).toBe(5000);
                expect(component.userName()).toBe('Jane');
            });

            it('should fail when fetching user data without user id', () => {
                authService.currentUserId.set(null);
                component.fetchUserData();
                httpMock.expectNone(`${apiUrl}/user/${testUserId}`);
            });

            it('should fail when fetching user data fails', () => {
                component.fetchUserData();
                const req = httpMock.expectOne(`${apiUrl}/user/${testUserId}`);
                req.error(new ErrorEvent('Network error'));
            });

            it('should fetch portfolio, prices, and calculate values', () => {
                const loadChartSpy = spyOn(component, 'loadChartData');
                const mockHoldings: Holding[] = [{ ticker: 'TSLA', quantity: 10, purchase_price: 200 }];
                const mockPrice = { latestPrice: 250 };

                component.fetchPortfolio();

                const holdingsReq = httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`);
                holdingsReq.flush(mockHoldings);

                const priceReq = httpMock.expectOne(`${apiUrl}/stock/TSLA`);
                priceReq.flush(mockPrice);

                expect(component.portfolioHoldings().length).toBe(1);
                expect(component.portfolioValue()).toBe(2500);
                expect(loadChartSpy).toHaveBeenCalledWith('1D');
            });

            it('should fail when fetching portfolio wihtout user id', () => {
                authService.currentUserId.set(null);
                component.fetchPortfolio();
                httpMock.expectNone(`${apiUrl}/holdings/${testUserId}`);
            });

            it('should return empty array when fetching portfolio with no holdings', () => {
                component.portfolioHoldings.set([]);
                component.fetchPortfolio();

                const req = httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`);
                expect(req.request.method).toBe('GET');
                req.flush([]);

                expect(component.portfolioHoldings().length).toBe(0);
            });

            // it('should fail when fetching portfolio fails', () => {
            //     component.fetchPortfolio();
            //     httpMock.expectOne(`${apiUrl}/holdings/${testUserId}`);
            //     const req = httpMock.expectOne(`${apiUrl}/stock/AAPL`);
            //     req.error(new ErrorEvent('Network error'));
            // })

            it('should fetch metrics and update signals', () => {
                const mockMetrics = { market_cap: 1e12, pe_ratio: 30, volume: 100000, dividend_yield: 0.015 };
                component.ticker = 'MSFT';
                component.fetchMetrics();
                const req = httpMock.expectOne(`${apiUrl}/metrics/MSFT`);
                req.flush(mockMetrics);
                expect(component.marketCap()).toBe(1e12);
            });

            it('should fetch activity and update signals', () => {
                const mockActivity: Activity[] = [
                    { action: 'BUY', ticker: 'AAPL', quantity: 10, price: 150, is_bot_trade: false, timestamp: '2023-01-01T10:00:00Z' },
                    { action: 'SELL', ticker: 'MSFT', quantity: 5, price: 200, is_bot_trade: true, timestamp: '2023-01-02T14:30:00Z' },
                ];
                component.fetchActivity();
                const req = httpMock.expectOne(`${apiUrl}/activity/${testUserId}`);
                req.flush(mockActivity);
                expect(component.recentActivity().length).toBe(2);
            });

            it('should fetch portfolioChange and portfolioProgress', () => {
                const mockHoldings: Holding[] = [{ ticker: 'AAPL', quantity: 10, purchase_price: 150 }];
                const mockPrices = new Map<string, number>([['AAPL', 180]]);
                component.portfolioHoldings.set(mockHoldings);
                component.currentPrices.set(mockPrices);

                // ((totalValue - InitialValue) / initialValue) * 100
                // ((1800 - 1500) / 1500) * 100 = 20
                expect(component.portfolioChange()).toBe(20);

                // Circumfrence - (Circumfrence * portfolioChange()) / 100
                const expectedProgress = 251.2 - (251.2 * 20) / 100;
                expect(component.portfolioProgress()).toBeCloseTo(expectedProgress, 1);            
            });

            it('should fetch portfolioChange given no change (empty portfolio)', () => {
                // Clear the default holdings so Initial Cost is 0
                component.portfolioHoldings.set([]); 
                component.portfolioValue.set(0); 

                expect(component.portfolioChange()).toBe(0); 
            });

            it('should fetch PortfolioCostBasis and totalPortfolioPLPct with no holdings', () => {
                component.portfolioHoldings.set([]); 
                component.portfolioValue.set(0); 

                expect(component.portfolioCostBasis()).toBe(0);
                expect(component.totalPortfolioPLPct()).toBe(0);
            
            });
        });

        describe('User Actions', () => {
            it('should toggle user menu', () => {
                expect(component.isUserMenuOpen()).toBe(false);
                component.toggleUserMenu();
                expect(component.isUserMenuOpen()).toBe(true);
                component.toggleUserMenu();
                expect(component.isUserMenuOpen()).toBe(false);
            })

            it('should close user menu', () => {
                expect(component.isUserMenuOpen()).toBe(false);
                component.toggleUserMenu();
                expect(component.isUserMenuOpen()).toBe(true);
                component.closeUserMenu();
                expect(component.isUserMenuOpen()).toBe(false);
            })

            it('should POST to deposit and update balance on success', () => {
                spyOn(window, 'prompt').and.returnValue('500');
                const mockResponse = { new_balance: 10500 };
                component.deposit();
                const req = httpMock.expectOne(`${apiUrl}/user/${testUserId}/deposit`);
                expect(req.request.method).toBe('POST');
                req.flush(mockResponse);
                expect(component.userBalance()).toBe(10500);
            });

            it('should get bot decision and update status', () => {
                const mockDecision = { decision: 'HOLD' };
                component.getBotDecision();
                const req = httpMock.expectOne(`${apiUrl}/bot/decision`);
                expect(req.request.method).toBe('POST');
                req.flush(mockDecision);
                expect(component.botStatus()).toBe('Decision: HOLD');
            });

            it('should log out and navigate to /login', () => {
                const navigateSpy = spyOn(router, 'navigate');
                component.logOut();
                const req = httpMock.expectOne(`${apiUrl}/logout`);
                req.flush({ message: 'Logged out' });
                expect(navigateSpy).toHaveBeenCalledWith(['/login']);
            });
        });

        describe('Chart Logic', () => {
            beforeEach(() => {
                component.portfolioHoldings.set([{ ticker: 'AAPL', quantity: 10, purchase_price: 150 }]);
            });

            it('should load chart data and call renderPortfolioChart', () => {
                const renderSpy = spyOn(component, 'renderPortfolioChart');
                const mockHistory = [{ timestamp: '2023-01-01T10:00:00Z', price: 155 }];

                component.loadChartData('1D');
                const req = httpMock.expectOne(`${apiUrl}/stock/AAPL/history?period=1D`);
                req.flush(mockHistory);

                expect(renderSpy).toHaveBeenCalled();
            });

            it('should destroy chart on ngOnDestroy', () => {
                const destroySpy = jasmine.createSpy('destroy');
                component.chart = { destroy: destroySpy } as any;
                component.ngOnDestroy();
                expect(destroySpy).toHaveBeenCalled();
            });
        });
    });

    // =========================================================
    // 2. Server Environment Suite
    // (Completely separate configuration)
    // =========================================================
    describe('Server Environment', () => {
        it('should not call fetch methods on ngOnInit on server', async () => {
            // Configure TestBed specifically for this test
            await TestBed.configureTestingModule({
                imports: [
                    HomepageComponent,
                    HttpClientTestingModule,
                    RouterTestingModule,
                ],
                providers: [
                    { provide: AuthService, useClass: MockAuthService },
                    { provide: BotStatusService, useClass: MockBotStatusService },
                    // FORCE PLATFORM TO SERVER HERE
                    { provide: PLATFORM_ID, useValue: 'server' }, 
                ],
            }).compileComponents();

            const serverFixture = TestBed.createComponent(HomepageComponent);
            const serverComponent = serverFixture.componentInstance;
            const serverAuth = TestBed.inject(AuthService) as unknown as MockAuthService;
            
            // Setup User ID so it doesn't fail on internal checks
            serverAuth.currentUserId.set(testUserId);

            const fetchUserDataSpy = spyOn(serverComponent, 'fetchUserData');
            const fetchPortfolioSpy = spyOn(serverComponent, 'fetchPortfolio');

            serverFixture.detectChanges(); // ngOnInit

            expect(fetchUserDataSpy).not.toHaveBeenCalled();
            expect(fetchPortfolioSpy).not.toHaveBeenCalled();
        });
    });
});