import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
import { importProvidersFrom } from '@angular/core';
import { MatGridListModule } from '@angular/material/grid-list';
import { HttpClient, provideHttpClient } from '@angular/common/http';
import { MatButtonModule} from '@angular/material/button';


bootstrapApplication(App, {
  providers: [
    importProvidersFrom(
      MatButtonModule,
      MatGridListModule,
      HttpClient,
    ),
    provideHttpClient(),
  ],
})
  .catch((err) => console.error(err));
