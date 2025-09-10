import { Routes } from '@angular/router';
import { DashboardComponent } from './dashboard/dashboard.component';

export const routes: Routes = [
    {
        path: '', // The "home page" URL (e.g., http://localhost:4200/)
        component: DashboardComponent // The component to display for this path
    }
];