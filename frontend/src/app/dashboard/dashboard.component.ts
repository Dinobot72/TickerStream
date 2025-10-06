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
export class DashboardComponent implements OnInit {
    userName: string = 'user';
    private apiUrl = 'http:localhost:8000/api';

    constructor(
    private route: ActivatedRoute,
    private http: HttpClient
  ) { }

    ngOnInit(): void {
        
    }

    getUserInfo() {
        this.http.get(`${this.apiUrl}/user`)
        this.userName = 'Dylan'
    }
}
