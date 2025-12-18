import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { PLATFORM_ID, signal } from '@angular/core';
import { Router } from '@angular/router';
import { of, Subject } from 'rxjs';
import { Chart, registerables } from 'chart.js';

import { HomepageComponent } from './homepage.component';
import { AuthService } from '../../auth.service';
import { BotStatusService } from '../../services/bot-status.service';

// Mocks
class MockAuthService {
    currentUserId = signal<string | null>(null);
}

class MockBotStatusService {
    private statusSubject = new Subject<boolean>();
    botStatus$ = this.statusSubject.asObservable();

    // Method to control the mock's emitted value
    setBotStatus(isActive: boolean) {
        this.statusSubject.next(isActive);
    }
}

// Redefine interfaces for test scope
interface Holding {
    ticker: string;
    quantity: number;
    purchase_price: number;
}

interface Activity {
    action: 'BUY' | 'SELL' | string;
    ticker: string;
    quantity: number;
    price: number;
    is_bot_trade: boolean;
    timestamp?: string;
}

describe('HomepageComponent', () => {
    let component: HomepageComponent;
    let fixture: ComponentFixture<HomepageComponent>;
    let httpMock: HttpTestingController;
    let authService: MockAuthService;
    let botStatusService: MockBotStatusService;
    let router: Router;

    const apiUrl = '/api';
    const testUserId = 'user-home-123';

    // Spy on Chart.js
    let chartConstructorSpy: jasmine.Spy;

    beforeAll(() => {
        // Chart.register is global, so it only needs to be done once.
        Chart.register(...registerables);
    });

    beforeEach(async () => {
        await TestBed.configureTestingModule({
            imports: [
                HomepageComponent,
                HttpClientTestingModule,
                RouterTestingModule.withRoutes([{ path: 'login', component: class Dummy {} }]), // For logout test
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

        // Set default user for most tests
        authService.currentUserId.set(testUserId);

        // Spy on the Chart constructor before each test
        chartConstructorSpy = spyOn(Chart.prototype, 'constructor' as any).and.callThrough();
    });

    afterEach(() => {
        httpMock.verify();
        component.ngOnDestroy(); // Manually call destroy to clean up chart
    });

    it('should create', () => {
        // Prevent ngOnInit calls for this simple creation test
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

        it('should not call fetch methods on ngOnInit on server', () => {
            TestBed.overrideProvider(PLATFORM_ID, { useValue: 'server' });
            const serverFixture = TestBed.createComponent(HomepageComponent);
            const serverComponent = serverFixture.componentInstance;
            
            const fetchUserDataSpy = spyOn(serverComponent, 'fetchUserData');
            const fetchPortfolioSpy = spyOn(serverComponent, 'fetchPortfolio');
            
            serverFixture.detectChanges(); // ngOnInit

            expect(fetchUserDataSpy).not.toHaveBeenCalled();
            expect(fetchPortfolioSpy).not.toHaveBeenCalled();
        });
    });

    describe('Data Fetching', () => {
        it('should fetch user data and update signals', () => {
            const mockUser = { balance: 5000, first_name: 'Jane' };
            component.fetchUserData();
            
            const req = httpMock.expectOne(`${apiUrl}/user/${testUserId}`);
            expect(req.request.method).toBe('GET');
            req.flush(mockUser);

            expect(component.userBalance()).toBe(5000);
            expect(component.userName()).toBe('Jane');
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
            expect(component.portfolioHoldings()[0].ticker).toBe('TSLA');
            expect(component.currentPrices().get('TSLA')).toBe(250);
            expect(component.portfolioValue()).toBe(2500); // 10 * 250
            expect(component.portfolioValueLive()).toBe(2500);
            expect(component.totalPortfolioPL()).toBe(500); // 2500 - 2000
            expect(loadChartSpy).toHaveBeenCalledWith('1D');
        });

        it('should fetch metrics and update signals', () => {
            const mockMetrics = { market_cap: 1e12, pe_ratio: 30, volume: 100000, dividend_yield: 0.015 };
            component.ticker = 'MSFT'; // Change ticker for test
            component.fetchMetrics();

            const req = httpMock.expectOne(`${apiUrl}/metrics/MSFT`);
            req.flush(mockMetrics);

            expect(component.marketCap()).toBe(1e12);
            expect(component.peRatio()).toBe(30);
            expect(component.volume()).toBe(100000);
            expect(component.dividendYield()).toBe(0.015);
        });
    });

    describe('User Actions', () => {
        it('should POST to deposit and update balance on success', () => {
            spyOn(window, 'prompt').and.returnValue('500');
            const mockResponse = { new_balance: 10500 };
            
            component.deposit();

            const req = httpMock.expectOne(`${apiUrl}/user/${testUserId}/deposit`);
            expect(req.request.method).toBe('POST');
            expect(req.request.body).toEqual({ amount: 500 });
            req.flush(mockResponse);

            expect(component.userBalance()).toBe(10500);
        });

        it('should get bot decision and update status', () => {
            const mockDecision = { decision: 'HOLD' };
            component.getBotDecision();

            expect(component.botStatus()).toBe('Thinking...');

            const req = httpMock.expectOne(`${apiUrl}/bot/decision`);
            expect(req.request.method).toBe('POST');
            req.flush(mockDecision);

            expect(component.botStatus()).toBe('Decision: HOLD');
        });

        it('should log out and navigate to /login', () => {
            const navigateSpy = spyOn(router, 'navigate');
            component.logOut();

            const req = httpMock.expectOne(`${apiUrl}/logout`);
            expect(req.request.method).toBe('POST');
            req.flush({ message: 'Logged out' });

            expect(navigateSpy).toHaveBeenCalledWith(['/login']);
        });
    });

    describe('Chart Logic', () => {
        beforeEach(() => {
            // Set some holdings to enable chart loading
            component.portfolioHoldings.set([{ ticker: 'AAPL', quantity: 10, purchase_price: 150 }]);
        });

        it('should load chart data and call renderPortfolioChart', () => {
            const renderSpy = spyOn(component, 'renderPortfolioChart');
            const mockHistory = [{ timestamp: '2023-01-01T10:00:00Z', price: 155 }];

            component.loadChartData('1D');
            expect(component.isChartLoading()).toBe(true);

            const req = httpMock.expectOne(`${apiUrl}/stock/AAPL/history?period=1D`);
            req.flush(mockHistory);

            expect(renderSpy).toHaveBeenCalledWith(
                [{ ticker: 'AAPL', quantity: 10, history: mockHistory }],
                '1D'
            );
            expect(component.isChartLoading()).toBe(false);
        });

        it('should destroy chart on ngOnDestroy', () => {
            const destroySpy = jasmine.createSpy('destroy');
            component.chart = { destroy: destroySpy } as any;
            
            component.ngOnDestroy();
            
            expect(destroySpy).toHaveBeenCalled();
        });
    });
});
