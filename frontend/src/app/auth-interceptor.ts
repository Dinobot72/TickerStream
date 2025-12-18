// auth-interceptor.ts
import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthService } from './auth.service';


export const authInterceptor: HttpInterceptorFn = (req, next) => {

  if ( req.url.startsWith('/api/')) {
    const authReq = req.clone({
        withCredentials: true,
    });
    return next( authReq );
  }
  return next( req );
};

