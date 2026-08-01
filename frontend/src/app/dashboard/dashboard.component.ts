import { CommonModule, isPlatformBrowser } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, PLATFORM_ID, signal } from '@angular/core'
import { MatGridListModule } from '@angular/material/grid-list';
import { SidebarComponent } from './sidebar/sidebar.comonent';
import { RouterModule } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { AuthService } from '../auth.service';


@Component({
    selector: 'dashboard',
    standalone: true,
    imports: [
        CommonModule,
        MatGridListModule,
        SidebarComponent,
        RouterModule
    ],
    providers: [],
    templateUrl: './dashboard.component.html',
    styleUrls: ['./dashboard.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent implements OnInit {
    userName = signal('User');
    private apiUrl = '/api';
    private authService = inject(AuthService);
    private http = inject(HttpClient);
    private platformId = inject(PLATFORM_ID);


    ngOnInit(): void {
        if (isPlatformBrowser(this.platformId)) {
            this.fetchUserName();
        }
    }

    fetchUserName(): void {
        const userId = this.authService.currentUserId();
        if (userId) {
            this.http.get<any>(`${this.apiUrl}/user/${userId}`, {withCredentials: true}).subscribe({
                next: (data) => {
                    this.userName.set(data.first_name);
                },
                error: (err) => {
                    console.error('Failed to fetch user name', err);
                }
            });
        }
    }
}
