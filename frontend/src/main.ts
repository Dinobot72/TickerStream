import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
import { importProvidersFrom } from '@angular/core';
import { MatGridListModule } from '@angular/material/grid-list';

bootstrapApplication(App, {
  providers: [
    importProvidersFrom(
      MatGridListModule,
    )
  ],
})
  .catch((err) => console.error(err));
