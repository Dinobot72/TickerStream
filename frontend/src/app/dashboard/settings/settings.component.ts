import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsComponent {
    // --- User Profile ---
    username = signal('dylanregan');
    firstName = signal('Dylan');
    lastName = signal('Regan');
    isLoadingProfile = signal(false);
    profileError = signal<string | null>(null);
    profileSuccess = signal<string | null>(null);

    // --- Password Change ---
    currentPassword = signal('');
    newPassword = signal('');
    confirmPassword = signal('');
    isChangingPassword = signal(false);
    passwordError = signal<string | null>(null);
    passwordSuccess = signal<string | null>(null);

     updateProfile(): void {
        this.profileError.set(null);
        this.profileSuccess.set(null);
        
        // Simulate update
        console.log('Updating profile (placeholder):', {
            firstName: this.firstName(),
            lastName: this.lastName()
        });
        
        this.profileSuccess.set('Profile updated successfully!');
        setTimeout(() => this.profileSuccess.set(null), 3000);
    }

     changePassword(): void {
        this.passwordError.set(null);
        this.passwordSuccess.set(null);
        this.isChangingPassword.set(true);

        if (this.newPassword() !== this.confirmPassword()) {
            this.passwordError.set('New passwords do not match.');
            this.isChangingPassword.set(false);
            return;
        }
        if (!this.currentPassword() || !this.newPassword()) {
             this.passwordError.set('Please fill in all password fields.');
             this.isChangingPassword.set(false);
            return;
        }

        // Simulate API call
        setTimeout(() => {
            this.passwordSuccess.set('Password changed successfully!');
            this.isChangingPassword.set(false);
            // Clear password fields
            this.currentPassword.set('');
            this.newPassword.set('');
            this.confirmPassword.set('');
             setTimeout(() => this.passwordSuccess.set(null), 3000);
        }, 1500);
    }
}

