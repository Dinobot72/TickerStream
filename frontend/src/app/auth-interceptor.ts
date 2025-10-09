import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthService } from './auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const authToken = authService.getToken();

  console.log('Interceptor token:', authToken);

  if ( authToken ) {
    const authReq = req.clone({
      setHeaders: {
        Authorization: `Bearer ${authToken}`
      }
    });
    console.log('Interceptor token header:', authReq.headers.get('Authorization')); // should print Bearer ...
    return next( authReq );
  }
  return next( req );
};

