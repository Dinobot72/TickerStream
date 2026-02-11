import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { FormsModule } from '@angular/forms';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { PLATFORM_ID, NgZone, ElementRef, signal } from '@angular/core';
import { Subject } from 'rxjs';

import { LoginComponent } from './login.component';
import { AuthService } from '../auth.service';

// --- Mocks ---

// Mock AuthService to control the observable stream for login
class MockAuthService {
    private loginResult = new Subject<any>();
    currentUserId = signal<string | null>(null); // Match the service interface

    login(credentials: any) {
        return this.loginResult.asObservable();
    }

    // Helper methods for tests to trigger success/error
    succeedLogin(response: any) {
        this.loginResult.next(response);
        this.loginResult.complete();
    }

    failLogin(error: any) {
        this.loginResult.error(error);
    }
}

// Mock ElementRef for canvas and ticker container
class MockElementRef<T> implements ElementRef {
    nativeElement: T;
    constructor(nativeEl: T) {
        this.nativeElement = nativeEl;
    }
}

describe('LoginComponent', () => {
    let component: LoginComponent;
    let fixture: ComponentFixture<LoginComponent>;
    let httpMock: HttpTestingController;
    let authService: MockAuthService;

    const apiUrl= 'https://auth.ticker-stream.com/api';

    // Mocks for canvas and its context
    let mockCanvas: HTMLCanvasElement;
    let mockCtx: CanvasRenderingContext2D;
    let mockTickerContainer: HTMLDivElement;

    beforeEach(async () => {
        // Create mock canvas context with spyable methods
        mockCtx = {
            clearRect: jasmine.createSpy('clearRect'),
            beginPath: jasmine.createSpy('beginPath'),
            lineTo: jasmine.createSpy('lineTo'),
            stroke: jasmine.createSpy('stroke'),
            lineWidth: 0,
            strokeStyle: ''
        } as any;

        // Create mock canvas element
        mockCanvas = {
            getContext: (contextId: string) => mockCtx,
            width: 1920,
            height: 1080
        } as any;

        // Create mock ticker container
        mockTickerContainer = {
            innerHTML: '',
            appendChild: jasmine.createSpy('appendChild')
        } as any;

        await TestBed.configureTestingModule({
            imports: [
                LoginComponent,
                HttpClientTestingModule,
                RouterTestingModule,
                FormsModule,
                NoopAnimationsModule,
            ],
            providers: [
                { provide: AuthService, useClass: MockAuthService },
                { provide: PLATFORM_ID, useValue: 'browser' }, // Default to browser
            ],
        }).compileComponents();

        fixture = TestBed.createComponent(LoginComponent);
        component = fixture.componentInstance;
        httpMock = TestBed.inject(HttpTestingController);
        authService = TestBed.inject(AuthService) as unknown as MockAuthService;

        // Manually set the ViewChild references to our mocks
        component.canvasRef = new MockElementRef(mockCanvas);
        component.tickerContainerRef = new MockElementRef(mockTickerContainer);

        // Spy on window methods
        spyOn(window, 'alert').and.stub();
        spyOn(console, 'error').and.stub();
    });

    afterEach(() => {
        httpMock.verify();
    });

    it('should create', () => {
        expect(component).toBeTruthy();
    });

    it('should have correct initial signal values', () => {
        expect(component.hidePassword()).toBe(true);
        expect(component.isLoginActive()).toBe(true);
    });

    describe('UI Toggles and Form State', () => {
        it('should toggle password visibility', () => {
            expect(component.hidePassword()).toBe(true);
            component.togglePasswordVisibility();
            expect(component.hidePassword()).toBe(false);
            component.togglePasswordVisibility();
            expect(component.hidePassword()).toBe(true);
        });

        it('should switch to login form and clear fields', () => {
            component.isLoginActive.set(false);
            component.username = 'test';
            component.showLoginForm();
            expect(component.isLoginActive()).toBe(true);
            expect(component.username).toBe('');
        });

        it('should switch to register form and clear fields', () => {
            component.isLoginActive.set(true);
            component.username = 'test';
            component.showRegisterForm();
            expect(component.isLoginActive()).toBe(false);
            expect(component.username).toBe('');
        });
    });

    describe('API Calls', () => {
        it('should call AuthService.login on login()', () => {
            const loginSpy = spyOn(authService, 'login').and.callThrough();
            component.username = 'testuser';
            component.password = 'password123';
            
            component.login();

            expect(loginSpy).toHaveBeenCalledWith({ username: 'testuser', password: 'password123' });
        });

        it('should handle failed login and show alert', () => {
            component.login();
            authService.failLogin({ error: 'Invalid credentials' });
            expect(console.error).toHaveBeenCalledWith('Login failed', { error: 'Invalid credentials' });
            expect(window.alert).toHaveBeenCalledWith('Invalid username or password');
        });

        it('should POST to register a new user and show alert on success', () => {
            const showLoginSpy = spyOn(component, 'showLoginForm');
            component.username = 'newuser';
            component.password = 'newpass';
            component.firstName = 'New';
            component.lastName = 'User';

            component.register();

            const req = httpMock.expectOne(`${apiUrl}/register`);
            expect(req.request.method).toBe('POST');
            expect(req.request.body).toEqual({
                username: 'newuser',
                password: 'newpass',
                first_name: 'New',
                last_name: 'User',
            });

            req.flush({ message: 'Success' });

            expect(window.alert).toHaveBeenCalledWith('Registration succesful! please log in');
            expect(showLoginSpy).toHaveBeenCalled();
        });
    });

    describe('Lifecycle and Animation', () => {
        it('should initialize canvas and tickers on ngAfterViewInit (browser)', () => {
            const initCanvasSpy = spyOn(component as any, 'initCanvas').and.callThrough();
            const startAnimationSpy = spyOn(component as any, 'startAnimationLoop').and.callThrough();
            const initTickerSpy = spyOn(component as any, 'initTickerStream').and.callThrough();
            const addEventSpy = spyOn(window, 'addEventListener');

            fixture.detectChanges(); // triggers ngAfterViewInit

            expect(initCanvasSpy).toHaveBeenCalled();
            expect(startAnimationSpy).toHaveBeenCalled();
            expect(initTickerSpy).toHaveBeenCalled();
            expect(addEventSpy).toHaveBeenCalledWith('resize', (component as any).onResize);
        });

        it('should NOT initialize canvas on ngAfterViewInit (server)', () => {
            TestBed.resetTestingModule();
            TestBed.configureTestingModule({
                imports: [LoginComponent, HttpClientTestingModule, RouterTestingModule, FormsModule, NoopAnimationsModule],
                providers: [
                    { provide: AuthService, useClass: MockAuthService },
                    { provide: PLATFORM_ID, useValue: 'server' }
                ]
            }).compileComponents();
            
            const serverFixture = TestBed.createComponent(LoginComponent);
            const serverComponent = serverFixture.componentInstance;
            
            const initCanvasSpy = spyOn(serverComponent as any, 'initCanvas');
            serverFixture.detectChanges();

            expect(initCanvasSpy).not.toHaveBeenCalled();
        });

        it('should clean up on ngOnDestroy', () => {
            const cancelAnimSpy = spyOn(window, 'cancelAnimationFrame');
            const removeEventSpy = spyOn(window, 'removeEventListener');
            (component as any).animationFrameId = 123;

            component.ngOnDestroy();

            expect(cancelAnimSpy).toHaveBeenCalledWith(123);
            expect(removeEventSpy).toHaveBeenCalledWith('resize', (component as any).onResize);
        });
    });
});