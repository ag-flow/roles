// Côté client (browser), tous les appels passent par le proxy Next.js
// (cf. ``app/api/[...path]/route.ts``) qui injecte le Bearer token de la
// session NextAuth côté serveur. ``API_BASE=''`` → URL relative same-origin.
//
// Côté SSR (Server Components), un caller qui veut taper directement le
// backend doit utiliser ``BACKEND_INTERNAL_URL`` + un fetch manuel avec le
// token de ``auth()`` (cf. usage dans ``app/page.tsx``).
const API_BASE = '';

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: string,
  ) {
    super(`API error ${status}: ${body}`);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init.headers,
    },
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body);
  }
  if (resp.status === 204) {
    return undefined as T;
  }
  return resp.json();
}

/**
 * Variante client-side qui injecte un Bearer token Keycloak.
 *
 * Le SSR (Server Components, route handlers) peut récupérer la session via `auth()`
 * et passer `session.accessToken` ; côté client, le caller récupère la session via
 * `useSession()` puis appelle ce helper.
 */
export async function apiFetchWithToken<T>(
  path: string,
  accessToken: string | undefined,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }
  if (!headers.has('Content-Type') && init.body) {
    headers.set('Content-Type', 'application/json');
  }

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  const resp = await fetch(`${apiUrl}${path}`, { ...init, headers });

  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body);
  }
  if (resp.status === 204) {
    return undefined as T;
  }
  return resp.json();
}
