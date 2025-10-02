import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from'@angular/core';
import { FormControl, FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';

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
})
export class LoginComponent {

    private apiUrl = 'http://localhost:8000/api'; 
    private router = inject(Router);

    usernameFormControl = new FormControl('');

    username: string = '';
    password: string = '';
    firstName: string = '';
    lastName: string = '';

    hide = signal(true);

    constructor( private http: HttpClient ) {}

    clickEvent(event: MouseEvent) {
        this.hide.set(!this.hide());
        event.stopPropagation();
    }

    login() {
        const credentials = {
            username: this.username,
            password: this.password,
        };

        this.http.post(`${this.apiUrl}/login`, credentials)
            .subscribe({
                next: (response: any) => {
                    console.log('Login Succesful', response)

                    // Save token + user info (you’ll need this later for API calls)
                    localStorage.setItem('token', response.access_token);
                    localStorage.setItem('user_id', response.user_id);

                    // Redirect after successful login
                    this.router.navigate(['/dashboard']);
                },
                error: (err) => {
                    console.error('Login failed', err);
                    alert("Invalid username or password");
                }
            })
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
                    this.login()
                },
                error: (err) => {
                    console.log('Registration Failed', err);
                }
            });
    }
}   
