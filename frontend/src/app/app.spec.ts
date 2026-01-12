import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { App } from './app';
import { provideRouter } from '@angular/router';
import { of, Subject, throwError } from 'rxjs';
import { error } from 'console';

class MockBotStatusService {
    private statusSubject = new Subject<boolean>();
    botStatus$ = this.statusSubject.asObservable();

    // Method to control the mock's emitted value
    setBotStatus(isActive: boolean) {
        this.statusSubject.next(isActive);
    }
}

import { BotStatusService } from './services/bot-status.service';

describe('App', () => {
  let botStatusServiceSpy: jasmine.SpyObj<BotStatusService>;
  let httpTestingController: HttpTestingController;

  beforeEach(async () => {
    botStatusServiceSpy = jasmine.createSpyObj('BotStatusService', ['checkBotStatus']);
    botStatusServiceSpy.checkBotStatus.and.returnValue(of({ status: 'active', message: 'Bot is running' }));

    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideZonelessChangeDetection(),
        provideRouter([]), // Provide an empty router for testing
        { provide: BotStatusService, useValue: botStatusServiceSpy } // Use the spy
      ]
    }).compileComponents();

    httpTestingController = TestBed.inject(HttpTestingController);
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
    expect(botStatusServiceSpy.checkBotStatus).toHaveBeenCalled();
  });

  it('should log an error if bot status check fails', () => {
    const consoleErrorSpy = spyOn(console, 'error');
    botStatusServiceSpy.checkBotStatus.and.returnValue(throwError(() => new Error('Bot status check failed')));

    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
    fixture.detectChanges();

    expect(consoleErrorSpy).toHaveBeenCalledWith('Failed to fetch bot status', jasmine.any(Error));
  });
});
