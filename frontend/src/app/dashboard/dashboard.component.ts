import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core'
import { MatGridListModule } from '@angular/material/grid-list';
import { SidebarComponent } from './sidebar/sidebar.comonent';
import { MainContentComponent } from './main-content/main-content.component';
import { ActivatedRoute } from '@angular/router';
import { HttpClient, HttpClientModule } from '@angular/common/http';
import { AuthService } from '../auth.service';


@Component({
    selector: 'dashboard',
    standalone: true,
    imports: [
        CommonModule,
        MatGridListModule,
        SidebarComponent,
        MainContentComponent,
        HttpClientModule,
    ],
    providers: [],
    templateUrl: './dashboard.component.html',
    styleUrls: ['./dashboard.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent implements OnInit {
    userName = signal('User');
    private apiUrl = 'http:localhost:8000/api';
    private authService = inject(AuthService);
    private http = inject(HttpClient);

    ngOnInit(): void {
        this.fetchUserName();
    }

    fetchUserName(): void {
        const userId = this.authService.getUserId();
        if (userId) {
            this.http.get<any>(`${this.apiUrl}/user/${userId}`).subscribe({
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
