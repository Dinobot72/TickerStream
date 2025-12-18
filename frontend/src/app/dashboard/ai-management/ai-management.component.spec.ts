import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { signal } from '@angular/core';

import { AiManagementComponent } from './ai-management.component';
import { AuthService } from '../../auth.service';
import { BotStatusService } from '../../services/bot-status.service';

// Redefine interfaces for test scope
interface Activity {
  action: 'BUY' | 'SELL';
  ticker: string;
  quantity: number;
  price: number;
  timestamp: string;
  is_bot_trade: boolean;
}

interface BotStatus {
  status: string;
  message?: string;
}

// Mocks
class MockAuthService {
    currentUserId = signal<string | null>(null);
}

class MockBotStatusService {} // Not used in component logic, but provided

describe('AiManagementComponent', () => {
    let component: AiManagementComponent;
    let fixture: ComponentFixture<AiManagementComponent>;
    let httpMock: HttpTestingController;
    let authService: MockAuthService;

    const apiUrl = '/api';
    const testUserId = 'user-ai-123';

    beforeEach(async () => {
        await TestBed.configureTestingModule({
            imports: [AiManagementComponent, HttpClientTestingModule],
            providers: [
                { provide: AuthService, useClass: MockAuthService },
                { provide: BotStatusService, useClass: MockBotStatusService },
            ],
        }).compileComponents();

        fixture = TestBed.createComponent(AiManagementComponent);
        component = fixture.componentInstance;
        httpMock = TestBed.inject(HttpTestingController);
        authService = TestBed.inject(AuthService) as unknown as MockAuthService;

        // Set default user for most tests
        authService.currentUserId.set(testUserId);
    });

    afterEach(() => {
        httpMock.verify();
    });

    it('should create', () => {
        spyOn(component, 'fetchBotStatus');
        spyOn(component, 'fetchBotActivity');
        fixture.detectChanges();
        expect(component).toBeTruthy();
    });

    it('should call fetch methods on ngOnInit', () => {
        const statusSpy = spyOn(component, 'fetchBotStatus');
        const activitySpy = spyOn(component, 'fetchBotActivity');
        fixture.detectChanges(); // ngOnInit
        expect(statusSpy).toHaveBeenCalled();
        expect(activitySpy).toHaveBeenCalled();
    });

    describe('Bot Status', () => {
        it('should fetch bot status and set to active', () => {
            const mockStatus: BotStatus = { status: 'active', message: 'Bot is running' };
            component.fetchBotStatus();
            const req = httpMock.expectOne(`${apiUrl}/bot/status`);
            req.flush(mockStatus);

            expect(component.isBotActive()).toBe(true);
            expect(component.botStatusMessage()).toBe('Bot is running');
            expect(component.isUpdatingStatus()).toBe(false);
        });

        it('should fetch bot status and set to inactive', () => {
            const mockStatus: BotStatus = { status: 'inactive', message: 'Bot is stopped' };
            component.fetchBotStatus();
            const req = httpMock.expectOne(`${apiUrl}/bot/status`);
            req.flush(mockStatus);

            expect(component.isBotActive()).toBe(false);
            expect(component.botStatusMessage()).toBe('Bot is stopped');
        });

        it('should handle error when fetching bot status', () => {
            component.fetchBotStatus();
            const req = httpMock.expectOne(`${apiUrl}/bot/status`);
            req.flush('Error', { status: 500, statusText: 'Server Error' });

            expect(component.isBotActive()).toBe(false);
            expect(component.botStatusMessage()).toBe('Error fetching status.');
        });

        it('should toggle bot from inactive to active', () => {
            component.isBotActive.set(false);
            const mockResponse: BotStatus = { status: 'active', message: 'Bot started successfully' };
            
            component.toggleBotStatus();
            expect(component.isUpdatingStatus()).toBe(true);
            expect(component.botStatusMessage()).toBe('Starting bot...');

            const req = httpMock.expectOne(`${apiUrl}/bot/start`);
            expect(req.request.method).toBe('POST');
            req.flush(mockResponse);

            expect(component.isBotActive()).toBe(true);
            expect(component.botStatusMessage()).toBe('Bot started successfully');
        });

        it('should toggle bot from active to inactive', () => {
            component.isBotActive.set(true);
            const mockResponse: BotStatus = { status: 'inactive', message: 'Bot stopped successfully' };

            component.toggleBotStatus();
            expect(component.isUpdatingStatus()).toBe(true);
            expect(component.botStatusMessage()).toBe('Stopping bot...');

            const req = httpMock.expectOne(`${apiUrl}/bot/stop`);
            expect(req.request.method).toBe('POST');
            req.flush(mockResponse);

            expect(component.isBotActive()).toBe(false);
            expect(component.botStatusMessage()).toBe('Bot stopped successfully');
        });
    });

    describe('Bot Activity', () => {
        it('should not fetch if user is not logged in', () => {
            authService.currentUserId.set(null);
            component.fetchBotActivity();
            expect(component.activityError()).toBe('User not logged in.');
            expect(component.isLoadingActivity()).toBe(false);
        });

        it('should fetch and filter bot activity, then calculate performance', () => {
            const calcSpy = spyOn(component, 'calculatePerformance');
            const mockActivities: Activity[] = [
                { action: 'BUY', ticker: 'AAPL', quantity: 1, price: 100, timestamp: '2023-01-02T10:00:00Z', is_bot_trade: true },
                { action: 'BUY', ticker: 'MSFT', quantity: 1, price: 200, timestamp: '2023-01-01T10:00:00Z', is_bot_trade: false }, // User trade
            ];

            component.fetchBotActivity();
            const req = httpMock.expectOne(`${apiUrl}/activity/${testUserId}?limit=50`);
            req.flush(mockActivities);

            expect(component.botActivityLog().length).toBe(1);
            expect(component.botActivityLog()[0].ticker).toBe('AAPL');
            expect(component.lastActionTime()).toBe('2023-01-02T10:00:00Z');
            expect(calcSpy).toHaveBeenCalledWith([mockActivities[0]]);
            expect(component.isLoadingActivity()).toBe(false);
        });

        it('should handle error when fetching bot activity', () => {
            component.fetchBotActivity();
            const req = httpMock.expectOne(`${apiUrl}/activity/${testUserId}?limit=50`);
            req.flush('Error', { status: 500, statusText: 'Server Error' });

            expect(component.activityError()).toBe('Could not load bot activity.');
            expect(component.botActivityLog().length).toBe(0);
        });
    });

    describe('Performance Calculation', () => {
        it('should handle empty activity list', () => {
            component.calculatePerformance([]);
            expect(component.botTotalPL()).toBe(0);
            expect(component.botWinRate()).toBe(0);
            expect(component.botTradesCount()).toBe(0);
        });

        it('should calculate performance for a simple win/loss scenario', () => {
            // API returns newest first, so we list them that way.
            // The calculation reverses for FIFO.
            const activities: Activity[] = [
                // Sell high (win)
                { action: 'SELL', ticker: 'AAPL', quantity: 1, price: 110, timestamp: '2023-01-04T10:00:00Z', is_bot_trade: true },
                // Sell low (loss)
                { action: 'SELL', ticker: 'GOOG', quantity: 1, price: 90, timestamp: '2023-01-03T10:00:00Z', is_bot_trade: true },
                // Buy low
                { action: 'BUY', ticker: 'AAPL', quantity: 1, price: 100, timestamp: '2023-01-02T10:00:00Z', is_bot_trade: true },
                // Buy high
                { action: 'BUY', ticker: 'GOOG', quantity: 1, price: 100, timestamp: '2023-01-01T10:00:00Z', is_bot_trade: true },
            ];

            component.calculatePerformance(activities);

            // P/L: (110 - 100) + (90 - 100) = 10 - 10 = 0
            expect(component.botTotalPL()).toBe(0);
            expect(component.botTradesCount()).toBe(4);
            // Win rate: 1 winning trade out of 2 closed pairs (this is tricky, the current logic counts all trades)
            // The current logic counts winning P/L events (1) / total trades (4) = 0.25
            expect(component.botWinRate()).toBe(1 / 4);
        });
    });
});
