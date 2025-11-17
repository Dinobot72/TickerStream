import { Component, signal, OnInit } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { BotStatusService } from './services/bot-status.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrls: ['./app.scss']
})
export class App implements OnInit {
  title = 'frontend';

  constructor(private botStatusService: BotStatusService) { }

  ngOnInit() {
    this.botStatusService.checkBotStatus().subscribe({
      error: (err) => console.error('Failed to fetch bot status', err)
    });
  }
}
