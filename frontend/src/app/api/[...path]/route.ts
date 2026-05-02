/**
 * Proxy générique frontend → backend.
 *
 * Toutes les requêtes ``/api/*`` reçues côté Next.js (sauf ``/api/auth/*``
 * qui est géré par le route handler [...nextauth] plus spécifique) sont
 * forwardées au backend FastAPI sur ``BACKEND_INTERNAL_URL`` avec un header
 * ``Authorization: Bearer <session.accessToken>`` injecté côté serveur.
 *
 * Pourquoi un proxy plutôt que des appels directs côté client ?
 *  - Le client (browser) n'a pas accès au accessToken stocké dans le cookie
 *    NextAuth (HttpOnly).
 *  - On évite d'exposer un endpoint ``/api/session-token`` qui sortirait
 *    le token côté JS.
 *  - Le backend reste joignable seulement depuis le LAN/réseau Docker —
 *    pas besoin d'un sous-domaine api-* exposé via Cloudflare Tunnel.
 *
 * Le proxy ne touche pas aux bodies (binaire ou JSON, peu importe). Il
 * propage les query params, le method, et la plupart des headers (sauf
 * ``host``/``connection`` qui sont réécrits par fetch).
 */

import { type NextRequest, NextResponse } from 'next/server';
import { auth } from '@/auth';

export const dynamic = 'force-dynamic';

const BACKEND_URL =
  process.env.BACKEND_INTERNAL_URL ?? 'http://backend:8000';

const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'transfer-encoding',
  'te',
  'trailer',
  'upgrade',
  'proxy-authenticate',
  'proxy-authorization',
  'host',
  'content-length', // fetch recompute
]);

async function forward(req: NextRequest, ctx: { params: { path: string[] } }) {
  const session = await auth();
  const path = ctx.params.path?.join('/') ?? '';
  const search = req.nextUrl.search;
  const targetUrl = `${BACKEND_URL}/api/${path}${search}`;

  const headers = new Headers();
  for (const [k, v] of req.headers.entries()) {
    if (!HOP_BY_HOP.has(k.toLowerCase())) headers.set(k, v);
  }
  if (session?.accessToken) {
    headers.set('Authorization', `Bearer ${session.accessToken}`);
  }

  // Body : pour GET/HEAD, fetch refuse un body. Sinon on streame.
  const method = req.method.toUpperCase();
  const hasBody = method !== 'GET' && method !== 'HEAD';
  const init: RequestInit = {
    method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
    redirect: 'manual',
    cache: 'no-store',
  };

  let backendResp: Response;
  try {
    backendResp = await fetch(targetUrl, init);
  } catch (err) {
    return NextResponse.json(
      {
        error: 'backend unreachable',
        target: targetUrl,
        cause: err instanceof Error ? err.message : String(err),
      },
      { status: 502 },
    );
  }

  const respHeaders = new Headers();
  for (const [k, v] of backendResp.headers.entries()) {
    if (!HOP_BY_HOP.has(k.toLowerCase())) respHeaders.set(k, v);
  }
  return new NextResponse(backendResp.body, {
    status: backendResp.status,
    statusText: backendResp.statusText,
    headers: respHeaders,
  });
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
export const HEAD = forward;
export const OPTIONS = forward;
