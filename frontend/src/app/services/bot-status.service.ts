import { Inject, Injectable, PLATFORM_ID } from "@angular/core";
import { HttpClient } from "@angular/common/http";
import { BehaviorSubject, Observable, of } from "rxjs";
import { catchError, tap } from "rxjs/operators";
import { isPlatformBrowser } from "@angular/common";

export interface BotStatus {
    status: string;
    message?: string;
}

@Injectable({
    providedIn: 'root'
})

export class BotStatusService {

    private readonly botStatusSubject = new BehaviorSubject<boolean>(false);
    public readonly botStatus$: Observable<boolean> = this.botStatusSubject.asObservable();

    private readonly botStatusMessageSubject = new BehaviorSubject<string>('Initializing...');
    public readonly botStatusMessage$: Observable<string> = this.botStatusMessageSubject.asObservable();

    private apiUrl = 'https://auth.ticker-stream.com/api/bot';


    constructor(
        private http: HttpClient,
        @Inject(PLATFORM_ID) private platformId: Object
    )   {
        // FIX: Only check status if we are in the Browser
        if (isPlatformBrowser(this.platformId)) {
            this.checkBotStatus().subscribe();
        }
    }

    /**
     * Gets the current bot status from the backend and updates the subjects.
     */
    checkBotStatus(): Observable<BotStatus | null> {
        if (!isPlatformBrowser(this.platformId)) {
            return of(null);
        }
        
        return this.http.get<BotStatus>(`${this.apiUrl}/status`, { withCredentials: true }).pipe(
            tap(status => {
                console.log("status update", status);
                const isActive = status.status === 'active';
                // Update both state and message subjects
                this.botStatusSubject.next(isActive);
                this.botStatusMessageSubject.next(status.message || (isActive ? 'Active' : 'Inactive'));
            }),
            catchError(err => {
                console.error('Failed to fetch bot status:', err);
                this.botStatusSubject.next(false);
                this.botStatusMessageSubject.next('Error fetching status.');
                return of(null); // Return null on error
            })
        );
    }

    /**
     * Sends a request to start the bot and updates the status on success.
     */
    startBot(): Observable<BotStatus | null> {
        return this.http.post<BotStatus>(`${this.apiUrl}/start`, {}, { withCredentials: true }).pipe(
            tap((status) => {
                // Update state based on the actual response
                const isActive = status.status === 'active';
                this.botStatusSubject.next(isActive);
                this.botStatusMessageSubject.next(status.message || (isActive ? 'Active' : 'Inactive'));
            }),
            catchError(err => {
                console.error('Failed to start bot:', err);
                this.botStatusMessageSubject.next(err.error?.detail || 'Error starting bot.');
                return of(null);
            })
        );
    }

    /**
     * Sends a request to stop the bot and updates the status on success.
     */
    stopBot(): Observable<BotStatus | null> {
        return this.http.post<BotStatus>(`${this.apiUrl}/stop`, {}, { withCredentials: true }).pipe(
            tap((status) => {
                // Update state based on the actual response
                const isActive = status.status === 'active';
                this.botStatusSubject.next(isActive);
                this.botStatusMessageSubject.next(status.message || (isActive ? 'Active' : 'Inactive'));
            }),
            catchError(err => {
                console.error('Failed to stop bot:', err);
                this.botStatusMessageSubject.next(err.error?.detail || 'Error stopping bot.');
                return of(null);
            })
        );
    }

    /**
     * A simple getter to synchronously check the current boolean value.
     */
    public get currentBotStatus(): boolean {
        return this.botStatusSubject.value;
    }
}