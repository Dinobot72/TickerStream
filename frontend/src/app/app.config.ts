import { ApplicationConfig, provideBrowserGlobalErrorListeners, provideZonelessChangeDetection, importProvidersFrom } from '@angular/core';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';
import { provideClientHydration, withEventReplay } from '@angular/platform-browser';
import { MatGridListModule } from '@angular/material/grid-list';
import { HttpClient, provideHttpClient, withFetch } from '@angular/common/http';
import { MatButtonModule} from '@angular/material/button';

export const appConfig: ApplicationConfig = {
  providers: [
    importProvidersFrom(
      MatButtonModule,
      MatGridListModule,
      HttpClient,
    ),
    provideHttpClient(),
    provideBrowserGlobalErrorListeners(),
    provideZonelessChangeDetection(),
    provideRouter(routes), 
    provideClientHydration(withEventReplay()),
    provideHttpClient(withFetch()),
  ]
};

