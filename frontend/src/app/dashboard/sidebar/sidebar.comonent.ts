import { CommonModule } from '@angular/common';
import { Component } from '@angular/core'

@Component({
    selector: 'sidebar',
    standalone: true,
    imports: [
        CommonModule,
    ],
    templateUrl: './sidebar.component.html',
    styleUrls: ['./sidebar.component.scss'],
})

export class SidebarComponent {

}