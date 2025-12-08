import { CommonModule } from '@angular/common';
import { Component } from '@angular/core'
import { RouterModule } from '@angular/router';

interface NavLink {
    path: string;
    label: string;
    iconSvgPath: string;
    exactMatch?: boolean;
}

@Component({
    selector: 'sidebar',
    standalone: true,
    imports: [
        CommonModule,
        RouterModule
    ],
    templateUrl: './sidebar.component.html',
    styleUrls: ['./sidebar.component.scss'],
})

export class SidebarComponent {
    navLinks: NavLink[] = [
        { path: '/dashboard', label: 'Dashboard', iconSvgPath: 'M10 2a8 8 0 100 16 8 8 0 000-16zM6.5 9a1.5 1.5 0 100 3 1.5 1.5 0 000-3zM10 12.5a2.5 2.5 0 110-5 2.5 2.5 0 010 5zM13.5 9a1.5 1.5 0 100 3 1.5 1.5 0 000-3z', exactMatch: true },
        { path: '/dashboard/positions', label: 'Positions', iconSvgPath: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
        { path: '/dashboard/watchlist', label: 'Watchlist', iconSvgPath: 'M15 12a3 3 0 11-6 0 3 3 0 016 0zM19.416 21.416a1 1 0 01-1.414 0l-2.828-2.828A7 7 0 1119.416 12a1 1 0 010 1.414l-2.828 2.828a1 1 0 01-1.414 0zM10 16a6 6 0 100-12 6 6 0 000 12z' },
        { path: '/dashboard/trading', label: 'Trading', iconSvgPath: 'M8 7l4-4m0 0l4 4m-4-4v18' },
        { path: '/dashboard/ai-management', label: 'AI Management', iconSvgPath: 'M10 20l4-16m-4 16L6 4m4 16l-4-16M6 4h12M6 4a2 2 0 100 4h12a2 2 0 100-4M6 20a2 2 0 100-4h12a2 2 0 100 4' },
        { path: '/dashboard/settings', label: 'Settings', iconSvgPath: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM10 13a3 3 0 100-6 3 3 0 000 6z' },
    ];

}