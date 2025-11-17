import { Injectable } from "@angular/core";
import { HttpClient } from "@angular/common/http";
import { BehaviorSubject, Observable } from "rxjs";
import { tap } from "rxjs/operators";

export interface BotStatus {
    isActive: boolean;
}

@Injectable({
    providedIn: 'root'
})

export class BotStatusService {

    private readonly botStatusSubject = new BehaviorSubject<boolean>(false);
    public readonly botStatus$: Observable<boolean> = this.botStatusSubject.asObservable();

    private apiUrl = 'http://localhost:8000/api/bot';


    constructor(private http: HttpClient) {
    // You can optionally check the status once when the service is first created.
    // this.checkBotStatus().subscribe();
    }

    /**
     * Gets the current bot status from the backend and updates the subject.
     */
    checkBotStatus(): Observable<BotStatus> {
        return this.http.get<BotStatus>(`${this.apiUrl}/status`).pipe(
            tap(status => {
                console.log("status update", status);
                // 3. When we get a response, update the subject.
                //    All subscribers will instantly get the new value.
                this.botStatusSubject.next(status.isActive);
            })
        );
    }

    /**
     * Sends a request to start the bot and updates the status on success.
     */
    startBot(): Observable<any> {
        return this.http.post(`${this.apiUrl}/start`, {}).pipe(
        tap(() => {
            // 4. On success, manually update the state to 'true'.
            this.botStatusSubject.next(true);
        })
        );
    }

    /**
     * Sends a request to stop the bot and updates the status on success.
     */
    stopBot(): Observable<any> {
        return this.http.post(`${this.apiUrl}/stop`, {}).pipe(
        tap(() => {
            // 5. On success, manually update the state to 'false'.
            this.botStatusSubject.next(false);
        })
        );
    }

    /**
     * A simple getter to synchronously check the current value,
     * though subscribing to botStatus$ is preferred.
     */
    public get currentBotStatus(): boolean {
        return this.botStatusSubject.value;
    }
}