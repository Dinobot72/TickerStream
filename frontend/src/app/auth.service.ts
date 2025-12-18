// auth.service.ts
import { Inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { tap, catchError } from 'rxjs/operators';
import { map, of, Observable } from 'rxjs';
import { response } from 'express';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = '/api';
  private isBrowser?: boolean;

  isLoggedIn = signal<boolean>(false);
  currentUserId = signal<string | null>(null);
  currentUsername = signal<string | null>(null);

  constructor(
    private http: HttpClient, 
    private router: Router,
    @Inject(PLATFORM_ID) private platformId: Object,
  ) {
    this.isBrowser = isPlatformBrowser(this.platformId);

    if (this.isBrowser) {
      this.checkAuthStatus().subscribe();
    }
  }

  login(credentials: {username: string, password: string}) {
    return this.http.post<any>(`${this.apiUrl}/login`, credentials, { withCredentials: true }).pipe(
      tap(response => {
        console.log('Login response:', response);
          this.isLoggedIn.set(true);
          this.currentUserId.set(response.user_id);
          this.currentUsername.set(response.username)
          this.router.navigate(['/dashboard']);
      })
    );
  }

  logout(): void {
    this.http.post(`${this.apiUrl}/logout`, {}, {withCredentials: true})
      .subscribe({
        next: () => {
          this.clearAuthState();
          this.router.navigate(['/login']);
        },
        error: () => {
          this.clearAuthState();
          this.router.navigate(['/login']);
        }
      });
  }

  private clearAuthState(): void {
    this.isLoggedIn.set(false);
    this.currentUserId.set(null);
    this.currentUsername.set(null);
  }

  checkAuthStatus(): Observable<boolean> {
    if (!this.isBrowser) {
        return of(false);
    }

    return this.http.get<{authenticated: boolean, user: any}>(`${this.apiUrl}/auth/status`, {
      withCredentials: true
    }).pipe(
      tap(response => {
        console.log('Auth status response:', response);
        if (response.authenticated) {
          this.isLoggedIn.set(true);
          this.currentUserId.set(response.user.user_id);
          this.currentUsername.set(response.user.username);
          console.log('User authenticated');
        } else {
          console.log('User not authenticated');
          this.clearAuthState();
        }
      }),
      map(response => response.authenticated),
      catchError(error => {
        console.error('Auth status check error:', error);
        this.clearAuthState();
        return of(false);
      })
    );
  }

  isAuthenticated(): Observable<boolean> {
    return this.checkAuthStatus();
  }
}
