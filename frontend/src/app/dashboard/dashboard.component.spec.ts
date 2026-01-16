import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { PLATFORM_ID, signal, Component } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';

import { DashboardComponent } from './dashboard.component';
import { AuthService } from '../auth.service';
import { SidebarComponent } from './sidebar/sidebar.comonent';
import { HomepageComponent } from './homepage/homepage.component';

// --- Mocks ---

class MockAuthService {
    currentUserId = signal<string | null>(null);
}

// Mock Child Components to prevent dependency errors from Sidebar/Homepage
@Component({selector: 'sidebar', standalone: true, template: ''})
class MockSidebarComponent {}

@Component({selector: 'homepage', standalone: true, template: ''})
class MockHomepageComponent {}

fdescribe('DashboardComponent', () => {
    let component: DashboardComponent;
    let fixture: ComponentFixture<DashboardComponent>;
    let httpMock: HttpTestingController;
    let authService: MockAuthService;

    const mockActivatedRoute = {
        snapshot: { params: {} },
        params: of({})
    };

    // Helper to configure TestBed (DRY principle)
    const configureTestBed = async (platform: 'browser' | 'server') => {
        await TestBed.configureTestingModule({
            imports: [DashboardComponent, HttpClientTestingModule],
            providers: [
                { provide: AuthService, useClass: MockAuthService },
                { provide: ActivatedRoute, useValue: mockActivatedRoute },
                { provide: PLATFORM_ID, useValue: platform }, // Inject Platform Here
            ],
        })
        .overrideComponent(DashboardComponent, {
            // Replace real child components with mocks to isolate Dashboard logic
            remove: { imports: [SidebarComponent, HomepageComponent] },
            add: { imports: [MockSidebarComponent, MockHomepageComponent] }
        })
        .compileComponents();

        fixture = TestBed.createComponent(DashboardComponent);
        component = fixture.componentInstance;
        httpMock = TestBed.inject(HttpTestingController);
        authService = TestBed.inject(AuthService) as unknown as MockAuthService;
    };

    afterEach(() => {
        httpMock.verify();
    });

    // =========================================================
    // 1. Server Environment Suite
    // =========================================================
    describe('on the server', () => {
        beforeEach(async () => {
            await configureTestBed('server');
        });

        it('should create but NOT call fetchUserName on ngOnInit', () => {
            const fetchSpy = spyOn(component, 'fetchUserName');
            fixture.detectChanges(); // ngOnInit
            expect(component).toBeTruthy();
            expect(fetchSpy).not.toHaveBeenCalled();
        });
    });

    // =========================================================
    // 2. Browser Environment Suite
    // =========================================================
    describe('on the browser', () => {
        beforeEach(async () => {
            await configureTestBed('browser');
        });

        it('should create and call fetchUserName on ngOnInit', () => {
            const fetchSpy = spyOn(component, 'fetchUserName');
            fixture.detectChanges(); // ngOnInit
            expect(component).toBeTruthy();
            expect(fetchSpy).toHaveBeenCalled();
            expect(component.userName()).toBe('User'); // Default value
        });

        it('should not make an HTTP request if user ID is null', () => {
            authService.currentUserId.set(null);
            fixture.detectChanges(); 
            // httpMock.verify() in afterEach ensures no request was made
            expect(component.userName()).toBe('User');
        });

        it('should fetch user name and update the signal on successful HTTP GET', () => {
            const testUserId = 'user-123';
            const mockUser = { first_name: 'John' };
            authService.currentUserId.set(testUserId);

            fixture.detectChanges(); // Triggers ngOnInit -> fetchUserName

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

            fixture.detectChanges();

            const req = httpMock.expectOne(`/api/user/${testUserId}`);
            req.flush('Server error', { status: 500, statusText: 'Internal Server Error' });

            expect(consoleErrorSpy).toHaveBeenCalledWith('Failed to fetch user name', jasmine.any(Object));
            expect(component.userName()).toBe('User'); // Remains default
        });
    });
});