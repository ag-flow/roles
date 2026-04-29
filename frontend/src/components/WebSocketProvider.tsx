'use client';

import { useEffect } from 'react';
import { useSession } from 'next-auth/react';
import type { ReactNode } from 'react';
import { wsManager } from '@/lib/ws/connection';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

function buildWsUrl(token: string): string {
  // http(s) → ws(s) en gardant le hostname/path
  const wsBase = API_BASE.replace(/^http/, 'ws');
  return `${wsBase}/ws?token=${encodeURIComponent(token)}`;
}

interface Props {
  children: ReactNode;
}

/**
 * Initialise la connexion WebSocket dès qu'une session authentifiée est
 * disponible. Le token JWT est passé en query param (le backend valide via
 * ``authenticate_websocket`` avant ``ws.accept()``).
 *
 * Au unmount (changement de page racine, déconnexion), ferme la WS et
 * stoppe le retry loop.
 *
 * Composant client : doit être rendu dans le layout root après un
 * ``<SessionProvider>`` (sinon ``useSession`` ne fonctionne pas).
 */
export function WebSocketProvider({ children }: Props) {
  const { data: session, status } = useSession();
  const accessToken =
    status === 'authenticated' ? session?.accessToken : undefined;

  useEffect(() => {
    if (!accessToken) return;
    wsManager.connect(buildWsUrl(accessToken));
    return () => {
      wsManager.disconnect();
    };
  }, [accessToken]);

  return <>{children}</>;
}
