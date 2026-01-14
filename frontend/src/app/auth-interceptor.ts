// auth-interceptor.ts
import { HttpInterceptorFn } from '@angular/common/http';

export const authInterceptor: HttpInterceptorFn = (req, next) => {

  if ( req.url.startsWith('/api/')) {
    const authReq = req.clone({
        withCredentials: true,
    });
    return next( authReq );
  }
  return next( req );
};
