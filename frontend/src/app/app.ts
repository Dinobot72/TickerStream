import { Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { DashboardComponent } from './dashboard/dashboard.component';
import { HttpClient } from '@angular/common/http'

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    DashboardComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App {
  protected readonly title = signal('stockBot');
}
