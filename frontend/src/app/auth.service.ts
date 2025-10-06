import { Inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { tap } from 'rxjs/operators';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = 'http://localhost:8000/api';
  private readonly TOKEN_KEY = 'auth_token';
  private readonly USER_ID_KEY ='auth_user_id';
  private isBrowser?: boolean;

  isLoggedIn = signal<boolean>(false);
  currentUserId = signal<string | null>(null);

  constructor(
    private http: HttpClient, 
    private router: Router,
    @Inject(PLATFORM_ID) private platformId: Object,
  ) {
    this.isBrowser = isPlatformBrowser(this.platformId);

    if (this.isBrowser) {
      this.isLoggedIn.set(this.hasToken());
      this.currentUserId.set(this.getUserId());
    }
  }

  login(credentials: {username: string, password: string}) {
    return this.http.post<any>(`${this.apiUrl}/login`, credentials).pipe(
      tap(response => {
        if (response && response.access_token) {
          this.setToken(response.access_token);
          this.setUserId(response.user_id);
          this.isLoggedIn.set(true);
          this.currentUserId.set(response.user_id);
          this.router.navigate(['/dashboard']);
        }
      })
    );
  }

  logout(): void {
    this.removeToken();
    this.removeUserId();
    this.isLoggedIn.set(false);
    this.currentUserId.set(null);
    this.router.navigate(['/login']);
  }

  getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  getUserId(): string | null {
    return localStorage.getItem(this.USER_ID_KEY);
  }

  private hasToken(): boolean {
    return !!this.getToken();
  }
  
  private setToken(token: string): void {
    localStorage.setItem(this.TOKEN_KEY, token);
  }

  private removeToken(): void {
    localStorage.removeItem(this.TOKEN_KEY);
  }

  private setUserId(userId: string): void {
    localStorage.setItem(this.USER_ID_KEY, userId.toString());
  }
  
  private removeUserId(): void {
    localStorage.removeItem(this.USER_ID_KEY);
  }
}
