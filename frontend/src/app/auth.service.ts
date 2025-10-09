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
      console.log('Login response:', response);
        if (response && response.access_token) {
          console.log('Saving Token:', response.access_token);
          this.setToken(response.access_token);
          this.setUserId(response.user_id);
          this.isLoggedIn.set(true);
          this.currentUserId.set(response.user_id);
          this.router.navigate(['/dashboard']);
        } else {
          console.error('No access_token in response!');
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
    if (this.isBrowser) {
      console.log('Returning TOKEN_KEY: ', this.TOKEN_KEY)
      return localStorage.getItem(this.TOKEN_KEY);
    }
    console.log('Not returning TOKEN_KEY')
    return null;
  }

  getUserId(): string | null {
    if (this.isBrowser) {
      return localStorage.getItem(this.USER_ID_KEY);
    }
    return null;
  }

  private hasToken(): boolean {
    return !!this.getToken();
  }
  
  private setToken(token: string): void {
    if (this.isBrowser) {
      localStorage.setItem(this.TOKEN_KEY, token);
    }
  }

  private removeToken(): void {
    if (this.isBrowser) {
      localStorage.removeItem(this.TOKEN_KEY);
    }
  }

  private setUserId(userId: string): void {
    if (this.isBrowser) {
      localStorage.setItem(this.USER_ID_KEY, userId.toString());
    }
  }
  
  private removeUserId(): void {
    if (this.isBrowser) {
      localStorage.removeItem(this.USER_ID_KEY);
    }
  }
}
