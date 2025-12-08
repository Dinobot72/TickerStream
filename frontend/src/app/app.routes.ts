import { NgModule } from '@angular/core'
import { RouterModule, Routes } from '@angular/router';
import { LoginComponent } from './login/login.component';
import { DashboardComponent } from './dashboard/dashboard.component';
import { HomepageComponent } from './dashboard/homepage/homepage.component';
import { PositionsComponent } from './dashboard/positions/positions.component';
import { WatchlistComponent } from './dashboard/watchlist/watchlist.component';
import { TradingComponent } from './dashboard/trading/trading.component';
import { AiManagementComponent } from './dashboard/ai-management/ai-management.component';
// import { OrdersComponent } from './dashboard/orders/orders.component';
import { SettingsComponent } from './dashboard/settings/settings.component';
import { authGuard } from './auth-guard';

export const routes: Routes = [
    {path: '', redirectTo: 'login', pathMatch: 'full'},
    {path: 'login', component: LoginComponent},
    {
        path: 'dashboard',
        component: DashboardComponent,
        canActivate: [authGuard],
        children: [
            { path: '', component: HomepageComponent },
            { path: 'positions', component: PositionsComponent },
            { path: 'watchlist', component: WatchlistComponent },
            { path: 'trading', component: TradingComponent },
            { path: 'ai-management', component: AiManagementComponent },
            { path: 'settings', component: SettingsComponent },
            { path: '**', redirectTo: '', pathMatch: 'full' }
        ]
    },
    {path: '**', redirectTo: 'login'},
];
