import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { PLATFORM_ID, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';

import { DashboardComponent } from './dashboard.component';
import { AuthService } from '../auth.service';

// Create a mock for AuthService to control its behavior in tests
class MockAuthService {
    // Use a signal to mimic the real service's behavior
    currentUserId = signal<string | null>(null);
}

describe('DashboardComponent', () => {
    let component: DashboardComponent;
    let fixture: ComponentFixture<DashboardComponent>;
    let httpMock: HttpTestingController;
    let authService: MockAuthService;

    // Mock for ActivatedRoute, which is a dependency of RouterModule
    const mockActivatedRoute = {
        // Provide a minimal snapshot mock
        snapshot: { params: {} },
        params: of({})
    };

    beforeEach(async () => {
        await TestBed.configureTestingModule({
            // Since DashboardComponent is standalone, we import it directly.
            imports: [DashboardComponent, HttpClientTestingModule],
            providers: [
                { provide: AuthService, useClass: MockAuthService },
                { provide: ActivatedRoute, useValue: mockActivatedRoute },
                // We will provide PLATFORM_ID specifically in nested describe blocks
            ],
        }).compileComponents();

        // Inject the testing controller for HTTP requests and the mock service
        httpMock = TestBed.inject(HttpTestingController);
        // Cast to our mock type for easier testing
        authService = TestBed.inject(AuthService) as unknown as MockAuthService;
    });

    afterEach(() => {
        // After each test, verify that there are no outstanding HTTP requests.
        httpMock.verify();
    });

    it('should create the component with a default user name', () => {
        fixture = TestBed.createComponent(DashboardComponent);
        component = fixture.componentInstance;
        fixture.detectChanges();
        expect(component).toBeTruthy();
        expect(component.userName()).toBe('User');
    });

    describe('on the server', () => {
        beforeEach(() => {
            // Reconfigure the TestBed to provide the 'server' platform ID
            TestBed.configureTestingModule({ providers: [{ provide: PLATFORM_ID, useValue: 'server' }] });
            fixture = TestBed.createComponent(DashboardComponent); // Re-create component after reconfiguring
            component = fixture.componentInstance;
        });

        it('should not call fetchUserName on ngOnInit', () => {
            // Spy on fetchUserName to check if it's called
            const fetchSpy = spyOn(component, 'fetchUserName');
            fixture.detectChanges(); // This triggers ngOnInit
            expect(fetchSpy).not.toHaveBeenCalled();
        });
    });

    describe('on the browser', () => {
        beforeEach(() => {
            // Reconfigure the TestBed to provide the 'browser' platform ID
            TestBed.configureTestingModule({ providers: [{ provide: PLATFORM_ID, useValue: 'browser' }] });
            fixture = TestBed.createComponent(DashboardComponent); // Re-create component after reconfiguring
            component = fixture.componentInstance;
        });

        it('should call fetchUserName on ngOnInit', () => {
            const fetchSpy = spyOn(component, 'fetchUserName');
            fixture.detectChanges(); // This triggers ngOnInit
            expect(fetchSpy).toHaveBeenCalled();
        });

        it('should not make an HTTP request if user ID is null', () => {
            authService.currentUserId.set(null);
            fixture.detectChanges(); // ngOnInit -> fetchUserName
            // httpMock.verify() in afterEach will ensure no request was made.
            expect(component.userName()).toBe('User');
        });

        it('should fetch user name and update the signal on successful HTTP GET', () => {
            const testUserId = 'user-123';
            const mockUser = { first_name: 'John' };
            authService.currentUserId.set(testUserId);

            fixture.detectChanges(); // ngOnInit -> fetchUserName

            const req = httpMock.expectOne(`/api/user/${testUserId}`);
            expect(req.request.method).toBe('GET');
            expect(req.request.withCredentials).toBe(true);

            req.flush(mockUser);
            expect(component.userName()).toBe(mockUser.first_name);
        });

        it('should log an error and not update user name on HTTP failure', () => {
            const consoleErrorSpy = spyOn(console, 'error');
            const testUserId = 'user-123';
            authService.currentUserId.set(testUserId);
            fixture.detectChanges(); // ngOnInit -> fetchUserName
            const req = httpMock.expectOne(`/api/user/${testUserId}`);
            req.flush('Server error', { status: 500, statusText: 'Internal Server Error' });
            expect(consoleErrorSpy).toHaveBeenCalledWith('Failed to fetch user name', jasmine.any(Object));
            expect(component.userName()).toBe('User');
        });
    });
});
