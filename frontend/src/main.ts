import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
import { importProvidersFrom } from '@angular/core';
import { MatGridListModule } from '@angular/material/grid-list';
import { HttpClient, provideHttpClient } from '@angular/common/http';

bootstrapApplication(App, {
  providers: [
    importProvidersFrom(
      MatGridListModule,
      HttpClient,
    ),
  ],
})
  .catch((err) => console.error(err));
