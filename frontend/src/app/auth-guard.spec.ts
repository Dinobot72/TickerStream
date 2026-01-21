import {RouterTestingHarness} from '@angular/router/testing';
import { provideRouter, Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { AuthService } from './auth.service';
import { authGuard } from './auth-guard';
import {Component} from '@angular/core';
import { Observable, of } from 'rxjs';


@Component({template: '<h1>Protected Page</h1>'})
class ProtectedComponent {}

@Component({template: '<h1>Login Page</h1>'})
class LoginComponent {}


describe('authGuard', () => {
  let authService: jasmine.SpyObj<AuthService>;
  let harness: RouterTestingHarness

  async function setup(isAuthenticated: Observable<boolean>) {
    authService = jasmine.createSpyObj('AuthService', ['isAuthenticated']);
    authService.isAuthenticated.and.returnValue(isAuthenticated);

    TestBed.configureTestingModule({
      providers: [
        {provide: AuthService, useValue: authService},
        provideRouter([
          {path: 'protected', component: ProtectedComponent, canActivate: [authGuard]},
          {path: 'login', component: LoginComponent}
        ]),
      ],
    })

    harness = await RouterTestingHarness.create();
  }

  it('allows navigation when user is authenticated', async () => {
    await setup(of(true));
    await harness.navigateByUrl('/protected', ProtectedComponent);
    // The protected component should render when authenticated
    expect(harness.routeNativeElement?.textContent).toContain('Protected Page');
  });

  it('redirects to login when user is not authenticated', async () => {
    await setup(of(false));
    await harness.navigateByUrl('/protected', LoginComponent);
    // The login component should render when not authenticated
    expect(harness.routeNativeElement?.textContent).toContain('Login Page');
  })
});
