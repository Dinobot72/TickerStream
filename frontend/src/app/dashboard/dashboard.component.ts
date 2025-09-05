import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, signal } from '@angular/core'
import { MatGridListModule } from '@angular/material/grid-list';
import { SidebarComponent } from './sidebar/sidebar.comonent';
import { MainContentComponent } from './main-content/main-conent.component';


@Component({
    selector: 'dashboard',
    standalone: true,
    imports: [
        CommonModule,
        MatGridListModule,
        SidebarComponent,
        MainContentComponent
    ],
    templateUrl: './dashboard.component.html',
    styleUrls: ['./dashboard.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent {
    
}
