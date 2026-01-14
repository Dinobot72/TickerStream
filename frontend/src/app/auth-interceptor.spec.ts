import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { authInterceptor } from './auth-interceptor';

describe('authInterceptor', () => {
  let httpTestingController: HttpTestingController;
  let httpClient: HttpClient;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ]
    });

    httpClient = TestBed.inject(HttpClient);
    httpTestingController = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTestingController.verify();
  });

  it('should add withCredentials: true for requests to /api/', () => {
    httpClient.get('/api/data').subscribe();

    const req = httpTestingController.expectOne('/api/data');

    expect(req.request.withCredentials).toBe(true);

    req.flush({});
  });

  it('should not modify requests not going to /api/', () => {
    httpClient.get('/assets/config.json').subscribe();

    const req = httpTestingController.expectOne('/assets/config.json');

    expect(req.request.withCredentials).toBe(false);

    req.flush({});
  });

  it('should not modify requests to a different domain', () => {
    httpClient.get('https://example.com/api/data').subscribe();

    const req = httpTestingController.expectOne('https://example.com/api/data');

    expect(req.request.withCredentials).toBe(false);

    req.flush({});
  });
});
