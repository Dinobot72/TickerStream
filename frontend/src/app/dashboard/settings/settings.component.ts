import { ChangeDetectionStrategy, Component, signal, OnInit, inject } from '@angular/core'; // Added OnInit, inject
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http'; // Added HttpClient
import { AuthService } from '../../auth.service'; // Added AuthService
import { catchError, finalize, of, tap } from 'rxjs'; // Added RxJS operators


@Component({
  selector: 'settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsComponent implements OnInit { // Implements OnInit
    private http = inject(HttpClient);
    private auth = inject(AuthService);
    private apiUrl = '/api';

    // --- User Profile ---
    username = signal('loading...'); // Initial state
    firstName = signal('');
    lastName = signal('');
    isLoadingProfile = signal(true); // Start loading
    profileError = signal<string | null>(null);
    profileSuccess = signal<string | null>(null);

    // --- Password Change ---
    currentPassword = signal('');
    newPassword = signal('');
    confirmPassword = signal('');
    isChangingPassword = signal(false);
    passwordError = signal<string | null>(null);
    passwordSuccess = signal<string | null>(null);

    ngOnInit(): void {
        this.fetchProfile();
    }

    fetchProfile(): void {
        const userId = this.auth.currentUserId();
        if (!userId) {
            this.profileError.set("User not logged in.");
            this.isLoadingProfile.set(false);
            return;
        }

        this.isLoadingProfile.set(true);
        this.profileError.set(null);

        this.http.get<any>(`${this.apiUrl}/user/${userId}`, { withCredentials: true })
            .pipe(
                catchError(err => {
                    console.error("Failed to fetch profile:", err);
                    this.profileError.set("Could not load profile data.");
                    return of(null); // Continue stream even on error
                }),
                finalize(() => this.isLoadingProfile.set(false))
            )
            .subscribe(data => {
                if (data) {
                    this.username.set(data.username);
                    this.firstName.set(data.first_name);
                    this.lastName.set(data.last_name);
                }
            });
    }


     updateProfile(): void {
        const userId = this.auth.currentUserId();
        if (!userId) {
            this.profileError.set("User not logged in.");
            return;
        }

        this.profileError.set(null);
        this.profileSuccess.set(null);
        this.isLoadingProfile.set(true); // Indicate loading during update

        const payload = {
            first_name: this.firstName(),
            last_name: this.lastName()
        };

        this.http.put<any>(`${this.apiUrl}/user/${userId}`, payload, { withCredentials: true })
            .pipe(
                catchError(err => {
                    console.error("Failed to update profile:", err);
                    this.profileError.set(err.error?.detail || "Failed to update profile.");
                    return of(null);
                }),
                finalize(() => this.isLoadingProfile.set(false))
            )
            .subscribe(response => {
                if (response) {
                    this.profileSuccess.set('Profile updated successfully!');
                    setTimeout(() => this.profileSuccess.set(null), 3000);
                }
                 // Error handled by catchError
            });
    }

     changePassword(): void {
        const userId = this.auth.currentUserId();
         if (!userId) {
            this.passwordError.set("User not logged in.");
            return;
        }

        this.passwordError.set(null);
        this.passwordSuccess.set(null);
        

        if (this.newPassword() !== this.confirmPassword()) {
            this.passwordError.set('New passwords do not match.');
            return;
        }
        if (!this.currentPassword() || !this.newPassword()) {
             this.passwordError.set('Please fill in all password fields.');
             return;
        }
        if (this.newPassword().length < 6) { // Example validation
             this.passwordError.set('New password must be at least 6 characters long.');
             return;
        }

        this.isChangingPassword.set(true);

        const payload = {
            current_password: this.currentPassword(),
            new_password: this.newPassword()
        };

        this.http.post<any>(`${this.apiUrl}/user/${userId}/change-password`, payload, { withCredentials: true })
           .pipe(
                catchError(err => {
                    console.error("Failed to change password:", err);
                    this.passwordError.set(err.error?.detail || "Failed to change password.");
                    return of(null);
                }),
                finalize(() => this.isChangingPassword.set(false))
            )
           .subscribe(response => {
                if (response) {
                    this.passwordSuccess.set('Password changed successfully!');
                    // Clear password fields
                    this.currentPassword.set('');
                    this.newPassword.set('');
                    this.confirmPassword.set('');
                    setTimeout(() => this.passwordSuccess.set(null), 3000);
                }
                // Error handled by catchError
            });
    }
}
