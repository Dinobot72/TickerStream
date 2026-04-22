import { TestBed } from "@angular/core/testing";
import { HttpClientTestingModule, HttpTestingController } from "@angular/common/http/testing";
import { PLATFORM_ID } from "@angular/core";

import { BotStatusService } from "./bot-status.service";
import { of } from "rxjs";

describe('BotStatusService', () => {
    let service: BotStatusService;
    let httpMock: HttpTestingController;

    beforeEach(() => {
        TestBed.configureTestingModule({
            imports: [HttpClientTestingModule],
            providers: [
                BotStatusService,
                { provide: PLATFORM_ID, useValue: 'browser' } // Assume browser environment for tests
            ]
        });

        service = TestBed.inject(BotStatusService);
        httpMock = TestBed.inject(HttpTestingController);

        httpMock.expectOne('/api/bot/status');
    });

    afterEach(() => {
        httpMock.verify(); // Ensure that there are no outstanding requests
    });

    it('should be created', () => {
        expect(service).toBeTruthy();
    });

    it('should call startBot and update status on success', () => {
        service.startBot().subscribe(status => {
            expect(status).toEqual({ status: 'active', message: 'Bot started successfully' });
        });
        const req = httpMock.expectOne('/api/bot/start');
        req.flush({ status: 'active', message: 'Bot started successfully' });
    });

    // it('should call startBot and update status on failure', () => {
    //     service.startBot().subscribe(
    //         () => fail('should have failed to start bot'),
    //         error => {
    //             expect(error).toBeNull(); // The service catches and returns of(null)
    //         }
    //     );
    //     const req = httpMock.expectOne('/api/bot/start');
    //     req.error(new ErrorEvent('Server error'), { status: 500, statusText: 'Server Error' });

    //     expect(service.currentBotStatus).toBeFalse(); // Initial state is false, should remain false
    //     service.botStatusMessage$.subscribe(message => expect(message).toBe('Error starting bot.')).unsubscribe();
    // });

    it('should call stopBot and update status on success', () => {
        service.stopBot().subscribe(status => {
            expect(status).toEqual({ status: 'inactive', message: 'Bot stopped successfully' });
        });
        const req = httpMock.expectOne('/api/bot/stop');
        req.flush({ status: 'inactive', message: 'Bot stopped successfully' })
    })

    it('should call checkBotStatus and update status on success', () => {
        service.startBot().subscribe(status => {
            expect(status).toEqual({ status: 'active', message: 'Bot started successfully' });
        });
        const reqStart = httpMock.expectOne('/api/bot/start');
        reqStart.flush({ status: 'active', message: 'Bot started successfully' });

        // Now check the bot status after starting it
        service.checkBotStatus().subscribe(status => {
            expect(status).toEqual({ status: 'active', message: 'Active' });
        });
        const reqStatusAfterStart = httpMock.expectOne('/api/bot/status');
        reqStatusAfterStart.flush({ status: 'active', message: 'Active' });

        // Stop the bot
        service.stopBot().subscribe(() => {
            // No explicit expectation here, as the next checkBotStatus will verify the state
        });
        const reqStop = httpMock.expectOne('/api/bot/stop');
        reqStop.flush({ status: 'inactive', message: 'Bot stopped successfully' });

        // Check the bot status after stopping it
        service.checkBotStatus().subscribe(status => {
            expect(status).toEqual({ status: 'inactive', message: 'Inactive' });
        });
        const reqStatusAfterStop = httpMock.expectOne('/api/bot/status');
        reqStatusAfterStop.flush({ status: 'inactive', message: 'Inactive' });
    });

    it('should get currentBotStatus as true', () => {
        service.startBot().subscribe();
        const req = httpMock.expectOne('/api/bot/start');
        req.flush({ status: 'active', message: 'Bot started successfully' });

        expect(service.currentBotStatus).toBeTrue();
    })

    it('should get currentBotStatus as false', () => {
        expect(service.currentBotStatus).toBeFalse();
    })
});