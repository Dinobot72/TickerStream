import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { Router } from '@angular/router';
import { AuthService } from './auth.service';
import { provideRouter } from '@angular/router';
import { PLATFORM_ID } from '@angular/core';

describe('AutheService', () => {
    let httpTesting: HttpTestingController;
    let service: AuthService;
    let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        AuthService,
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
      ]
    });
    httpTesting = TestBed.inject(HttpTestingController);
    service = TestBed.inject(AuthService);
    router = TestBed.inject(Router);

    const initReq = httpTesting.expectOne('/api/auth/status');
    initReq.flush({ authenticated: false });
  });

  afterEach(() => {
    httpTesting.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should succesfully login', () => {
    const mockCredentials = { username: 'testuser', password: 'testpassword' };
    const mockResponse = { user_id: '123', username: 'testuser' };
    const router = TestBed.inject(Router);
    const navigateSpy = spyOn(router, 'navigate');

    service.login(mockCredentials).subscribe(response => {
      expect(service.isLoggedIn()).toBe(true);
      expect(response).toEqual(mockResponse);
      expect(service.currentUserId()).toBe(mockResponse.user_id);
      expect(service.currentUsername()).toBe(mockResponse.username);
      expect(navigateSpy).toHaveBeenCalledWith(['/dashboard']);
    });
    
    const req = httpTesting.expectOne('/api/login');
    expect(req.request.method).toBe('POST');
    req.flush(mockResponse);
  });

  it('should succesfully logout', () => {
    service.isLoggedIn.set(true);
    service.currentUserId.set('123');
    service.currentUsername.set('testuser');
    const navigateSpy = spyOn(router, 'navigate');

    service.logout();

    const req = httpTesting.expectOne('/api/logout');
    expect(req.request.method).toBe('POST');
    req.flush({});

    expect(service.isLoggedIn()).toBe(false);
    expect(service.currentUserId()).toBe(null);
    expect(service.currentUsername()).toBe(null);
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
  });

  it('should clear state and redirect if logout fails', () => {
    service.isLoggedIn.set(true);
    const navigateSpy = spyOn(router, 'navigate');

    service.logout();

    const req = httpTesting.expectOne('/api/logout');
    req.flush('Something went wrong', { status: 500, statusText: 'Server Error' });

    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
    expect(service.isLoggedIn()).toBe(false);

  });

  it('should update state when checkAuthStatus returns authenticated', () => {
    const mockUser = { user_id: '888', username: 'returning_user' };
    
    // 1. Manually call checkAuthStatus (this triggers a NEW request)
    service.checkAuthStatus().subscribe(isAuthenticated => {
      expect(isAuthenticated).toBe(true);
    });

    // 2. Handle the request
    const req = httpTesting.expectOne('/api/auth/status');
    req.flush({ authenticated: true, user: mockUser });

    // 3. Verify signals were updated
    expect(service.isLoggedIn()).toBe(true);
    expect(service.currentUserId()).toBe('888');
    expect(service.currentUsername()).toBe('returning_user');
  });

  it('should clear state when checkAuthStatus returns HTTP error', () => {
    // 1. Pretend we are locally logged in
    service.isLoggedIn.set(true);

    // 2. Call checkAuthStatus
    service.checkAuthStatus().subscribe(isAuthenticated => {
      expect(isAuthenticated).toBe(false); // Should return false on error
    });

    // 3. Simulate a Network Error
    const req = httpTesting.expectOne('/api/auth/status');
    req.flush('Network error', { status: 500, statusText: 'Error' });

    // 4. Verify state was wiped
    expect(service.isLoggedIn()).toBe(false);
  });

  it('should check authentication status via isAuthenticated helper', () => {
    service.isLoggedIn.set(true);
    expect(service.isAuthenticated()).toBe(true);
    
    service.isLoggedIn.set(false);
    expect(service.isAuthenticated()).toBe(false);
  });
});

describe('AuthService (Server Platform)', () => {
  let service: AuthService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        AuthService,
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: PLATFORM_ID, useValue: 'server' } 
      ]
    });
    service = TestBed.inject(AuthService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
  });

  it('should NOT check auth status automatically on construction', () => {
    expect(service).toBeTruthy();
  });

  it('should return false immediately for checkAuthStatus', () => {
    let result: boolean | undefined;
    
    service.checkAuthStatus().subscribe(val => result = val);
    
    expect(result).toBe(false);
  });
});
