import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { FormsModule } from '@angular/forms';
import { signal } from '@angular/core';

import { SettingsComponent } from './settings.component';
import { AuthService } from '../../auth.service';

// Mock AuthService to control the currentUserId signal in tests
class MockAuthService {
    currentUserId = signal<string | null>(null);
}

describe('SettingsComponent', () => {
    let component: SettingsComponent;
    let fixture: ComponentFixture<SettingsComponent>;
    let httpMock: HttpTestingController;
    let authService: MockAuthService;
    const apiUrl = 'http://localhost:8000/api';
    const testUserId = 'user-test-123';

    beforeEach(async () => {
        await TestBed.configureTestingModule({
            imports: [
                SettingsComponent, // It's a standalone component
                FormsModule,
                HttpClientTestingModule
            ],
            providers: [
                { provide: AuthService, useClass: MockAuthService }
            ]
        }).compileComponents();

        fixture = TestBed.createComponent(SettingsComponent);
        component = fixture.componentInstance;
        httpMock = TestBed.inject(HttpTestingController);
        authService = TestBed.inject(AuthService) as unknown as MockAuthService;

        // Set a default user for most tests
        authService.currentUserId.set(testUserId);
    });

    afterEach(() => {
        // Ensure that there are no outstanding HTTP requests after each test
        httpMock.verify();
    });

    it('should create', () => {
        spyOn(component, 'fetchProfile').and.stub(); // Prevent ngOnInit call for this simple test
        fixture.detectChanges();
        expect(component).toBeTruthy();
    });

    it('should call fetchProfile on ngOnInit', () => {
        const fetchProfileSpy = spyOn(component, 'fetchProfile');
        fixture.detectChanges(); // Triggers ngOnInit
        expect(fetchProfileSpy).toHaveBeenCalled();
    });

    describe('User Profile', () => {
        describe('fetchProfile', () => {
            it('should set an error if user is not logged in', () => {
                authService.currentUserId.set(null);
                component.fetchProfile();
                expect(component.profileError()).toBe('User not logged in.');
                expect(component.isLoadingProfile()).toBe(false);
            });

            it('should fetch profile data and update signals on success', () => {
                const mockProfile = {
                    username: 'testuser',
                    first_name: 'Test',
                    last_name: 'User'
                };

                component.fetchProfile();

                const req = httpMock.expectOne(`${apiUrl}/user/${testUserId}`);
                expect(req.request.method).toBe('GET');
                req.flush(mockProfile);

                expect(component.isLoadingProfile()).toBe(false);
                expect(component.username()).toBe('testuser');
                expect(component.firstName()).toBe('Test');
                expect(component.lastName()).toBe('User');
                expect(component.profileError()).toBeNull();
            });

            it('should set an error on failed profile fetch', () => {
                component.fetchProfile();

                const req = httpMock.expectOne(`${apiUrl}/user/${testUserId}`);
                req.flush('Error', { status: 500, statusText: 'Server Error' });

                expect(component.isLoadingProfile()).toBe(false);
                expect(component.profileError()).toBe('Could not load profile data.');
                expect(component.username()).toBe('loading...'); // Initial value
            });
        });

        describe('updateProfile', () => {
            it('should set an error if user is not logged in', () => {
                authService.currentUserId.set(null);
                component.updateProfile();
                expect(component.profileError()).toBe('User not logged in.');
            });

            it('should send a PUT request and show success message', fakeAsync(() => {
                const newFirstName = 'UpdatedFirst';
                const newLastName = 'UpdatedLast';
                component.firstName.set(newFirstName);
                component.lastName.set(newLastName);

                component.updateProfile();

                const req = httpMock.expectOne(`${apiUrl}/user/${testUserId}`);
                expect(req.request.method).toBe('PUT');
                expect(req.request.body).toEqual({ first_name: newFirstName, last_name: newLastName });

                req.flush({ message: 'Profile updated successfully!' });

                expect(component.isLoadingProfile()).toBe(false);
                expect(component.profileSuccess()).toBe('Profile updated successfully!');

                tick(3000);
                expect(component.profileSuccess()).toBeNull();
            }));

            it('should set an error on failed profile update', () => {
                component.updateProfile();

                const req = httpMock.expectOne(`${apiUrl}/user/${testUserId}`);
                req.flush({ detail: 'Update failed' }, { status: 400, statusText: 'Bad Request' });

                expect(component.isLoadingProfile()).toBe(false);
                expect(component.profileError()).toBe('Update failed');
                expect(component.profileSuccess()).toBeNull();
            });
        });
    });

    describe('Password Change', () => {
        it('should set an error if user is not logged in', () => {
            authService.currentUserId.set(null);
            component.changePassword();
            expect(component.passwordError()).toBe('User not logged in.');
        });

        it('should set an error if new passwords do not match', () => {
            component.newPassword.set('newPass123');
            component.confirmPassword.set('newPass456');
            component.changePassword();
            expect(component.passwordError()).toBe('New passwords do not match.');
        });

        it('should set an error if any password field is empty', () => {
            component.currentPassword.set('');
            component.newPassword.set('newPass123');
            component.confirmPassword.set('newPass123');
            component.changePassword();
            expect(component.passwordError()).toBe('Please fill in all password fields.');
        });

        it('should send a POST request and show success on valid password change', fakeAsync(() => {
            component.currentPassword.set('oldPassword123');
            component.newPassword.set('newPassword123');
            component.confirmPassword.set('newPassword123');

            component.changePassword();
            expect(component.isChangingPassword()).toBe(true);

            const req = httpMock.expectOne(`${apiUrl}/user/${testUserId}/change-password`);
            expect(req.request.method).toBe('POST');
            expect(req.request.body).toEqual({ current_password: 'oldPassword123', new_password: 'newPassword123' });

            req.flush({ message: 'Password changed successfully!' });

            expect(component.isChangingPassword()).toBe(false);
            expect(component.passwordSuccess()).toBe('Password changed successfully!');
            expect(component.currentPassword()).toBe('');
            expect(component.newPassword()).toBe('');
            expect(component.confirmPassword()).toBe('');

            tick(3000);
            expect(component.passwordSuccess()).toBeNull();
        }));

        it('should set an error on failed password change', () => {
            component.currentPassword.set('wrongOldPassword');
            component.newPassword.set('newPassword123');
            component.confirmPassword.set('newPassword123');

            component.changePassword();
            expect(component.isChangingPassword()).toBe(true);

            const req = httpMock.expectOne(`${apiUrl}/user/${testUserId}/change-password`);
            req.flush({ detail: 'Incorrect current password' }, { status: 400, statusText: 'Bad Request' });

            expect(component.isChangingPassword()).toBe(false);
            expect(component.passwordError()).toBe('Incorrect current password');
            expect(component.passwordSuccess()).toBeNull();
        });
    });
});
