import { CommonModule, isPlatformBrowser } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal, AfterViewInit, OnDestroy, ElementRef, ViewChild, PLATFORM_ID, NgZone } from '@angular/core';
import { FormControl, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
    selector: 'login-page',
    standalone: true,
    imports: [
        MatCardModule,
        MatDividerModule,
        MatFormFieldModule,
        MatInputModule,
        CommonModule,
        FormsModule,
        MatIconModule,
        MatButtonModule,
    ],
    templateUrl: './login.component.html',
    styleUrls: ['./login.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent implements AfterViewInit, OnDestroy {

    private apiUrl = '/api'; 
    private authService = inject(AuthService);
    private platformId = inject(PLATFORM_ID);
    private ngZone = inject(NgZone);

    @ViewChild('marketWaveCanvas') canvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('tickerStreamContainer') tickerContainerRef!: ElementRef<HTMLDivElement>;

    username: string = '';
    password: string = '';
    firstName: string = '';
    lastName: string = '';

    hidePassword = signal(true);
    isLoginActive = signal(true);

    // Animation variables
    private animationFrameId: number | null = null;
    private canvas!: HTMLCanvasElement;
    private ctx!: CanvasRenderingContext2D;
    private w!: number;
    private h!: number;
    private time = 0;

    private waves = [
        { amp: 50, freq: 0.01, speed: 0.015, color: 'rgba(0, 230, 118, 0.2)', width: 2 }, // Green
        { amp: 60, freq: 0.008, speed: 0.01, color: 'rgba(255, 82, 82, 0.2)', width: 2 },   // Red
        { amp: 70, freq: 0.005, speed: 0.02, color: 'rgba(0, 191, 255, 0.3)', width: 3 }    // Blue (from CSS variables)
    ];
    private tickerSymbols = ['TKS.AI', 'GLOBL', 'FINX', 'NVDA', 'TSLA', 'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'BTC', 'ETH', 'SOL'];
    private tickerRowCount = 15;

    constructor( private http: HttpClient ) {}

    ngAfterViewInit(): void {
        if (isPlatformBrowser(this.platformId)) {
            this.ngZone.runOutsideAngular(() => {
                this.initCanvas();
                this.startAnimationLoop();
                this.initTickerStream();

                window.addEventListener('resize', this.onResize);
            });
        }
    }

    ngOnDestroy(): void {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
        }
        if (isPlatformBrowser(this.platformId)) {
            window.removeEventListener('resize', this.onResize);
        }
    }

    togglePasswordVisibility(): void {
        this.hidePassword.set(!this.hidePassword());
    }

    showLoginForm(): void {
        this.isLoginActive.set(true);
        this.clearForm();
    }

    showRegisterForm(): void {
        this.isLoginActive.set(false);
        this.clearForm();
    }

    clearForm(): void {
        this.username = '';
        this.password = '';
        this.firstName = '';
        this.lastName = '';
    }

    login(): void {
        console.log('username: ', this.username,' password: ', this.password)
        this.authService.login({ username: this.username, password: this.password })
            .subscribe({
                next: (response) => {
                    console.log('Login successful from component', response);
                },
                error: (err) => {
                    console.error('Login failed', err);
                    alert("Invalid username or password");
                }
            });
    }

    register() {

        const user = {
            username: this.username,
            password: this.password,
            first_name: this.firstName,
            last_name: this.lastName,
        };

        this.http.post(`${this.apiUrl}/register`, user)
            .subscribe({
                next: (response) => {
                    console.log('Regestration succesful', response);
                    alert('Registration succesful! please log in');
                    this.showLoginForm();
                },
                error: (err) => {
                    console.log('Registration Failed', err);
                }
            });
    }

    private initCanvas(): void {
        const canvas = this.canvasRef?.nativeElement;
        if (!canvas) {
            console.error('Canvas element not found!');
            return;
        }
        const context = canvas.getContext('2d');
        if (!context) {
            console.error('Could not get 2D context for canvas!');
            return;
        }
        this.ctx = context;
        this.w = canvas.width = window.innerWidth;
        this.h = canvas.height = window.innerHeight;
    }

    private startAnimationLoop = (): void => {
         this.drawWave();
         this.animationFrameId = requestAnimationFrame(this.startAnimationLoop);
    }
    
    private drawWave = (): void => {
        if (!this.ctx) return;
    
        // Clear Rect
        this.ctx.clearRect(0, 0, this.w, this.h);
        this.time += 0.02;
    
        this.waves.forEach(wave => {
            this.ctx!.beginPath();
            this.ctx!.lineWidth = wave.width;
            this.ctx!.strokeStyle = wave.color;
    
            for (let x = 0; x < this.w; x++) {
                // The Math from your snippet
                const y = this.h / 2 + Math.sin(x * wave.freq + this.time * wave.speed) * wave.amp * Math.sin(this.time * 0.1);
                this.ctx!.lineTo(x, y);
            }
            this.ctx!.stroke();
        });
    }

    private initTickerStream(): void {
        const container = this.tickerContainerRef?.nativeElement;
        if (!container) return;

        container.innerHTML = ''; // Clear existing

        for (let i = 0; i < this.tickerRowCount; i++) {
            const row = document.createElement('div');
            row.className = 'ticker-row';
            
            // Exact styling logic from your snippet
            row.style.top = `${Math.random() * 100}%`;
            row.style.animationDuration = `${Math.random() * 40 + 40}s`;
            row.style.animationDelay = `${Math.random() * -60}s`;
            row.style.opacity = `${Math.random() * 0.3 + 0.1}`;
            
            row.innerHTML = this.generateTickerContent();
            container.appendChild(row);
        }
    }

    private generateTickerContent(): string {
        let content = '';
        // Generate enough content to fill the screen width multiple times for seamless looping
        for(let i = 0; i < 100; i++) { // Adjust count based on typical screen widths
            const symbol = this.tickerSymbols[Math.floor(Math.random() * this.tickerSymbols.length)];
            const change = (Math.random() * 5 - 2.5).toFixed(2); // Random change +/- 2.5%
            const className = Number(change) >= 0 ? 'gain' : 'loss';
            content += `<span class="${className}">${symbol} ${Number(change) > 0 ? '+' : ''}${change}%</span>`;
        }
        return content + content; // Duplicate content for smooth scrolling illusion
    }

    private onResize = (): void => {
        this.ngZone.runOutsideAngular(() => {
            this.initCanvas();
            this.initTickerStream();
        });
    }
}
