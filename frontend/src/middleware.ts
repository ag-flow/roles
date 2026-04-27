import { auth } from '@/auth';

export default auth((req) => {
  const isLoginPage = req.nextUrl.pathname.startsWith('/login');
  if (!req.auth && !isLoginPage) {
    const loginUrl = new URL('/login', req.nextUrl.origin);
    return Response.redirect(loginUrl);
  }
});

export const config = {
  matcher: [
    // Exclure : assets Next, api/auth, favicon, fichiers statiques
    '/((?!_next/static|_next/image|api/auth|favicon.ico|.*\\.).*)',
  ],
};
