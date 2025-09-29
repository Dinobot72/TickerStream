import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, OnInit, signal } from '@angular/core'
import { MatGridListModule } from '@angular/material/grid-list';
import { SidebarComponent } from './sidebar/sidebar.comonent';
import { MainContentComponent } from './main-content/main-content.component';
import { ActivatedRoute } from '@angular/router';
import { HttpClient, HttpClientModule } from '@angular/common/http';


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
export class DashboardComponent implements OnInit{
    userName: string = 'user';
    private apiUrl = 'http:localhost:8000/api';

    constructor(
    private route: ActivatedRoute,
    private http: HttpClient
  ) {}

    ngOnInit(): void {
    this.route.paramMap.subscribe(params => {
      const userId = params.get('userId');
      if (userId) {
        this.fetchUserDetails(userId);
      }
    });
  }

  fetchUserDetails(userId: string): void {
    this.http.get<any>(`${this.apiUrl}/user/${userId}`).subscribe({
      next: (user) => {
        this.userName = user.first_name;
      },
      error: (err) => {
        console.error('Failed to fetch user details', err);
      }
    });
  }
}
