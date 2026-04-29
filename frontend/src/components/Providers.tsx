'use client';

import { SessionProvider } from 'next-auth/react';
import type { ReactNode } from 'react';
import { WebSocketProvider } from './WebSocketProvider';

/**
 * Wrapper client qui compose les providers nécessaires côté client :
 * - ``SessionProvider`` : expose ``useSession()`` aux composants enfants
 * - ``WebSocketProvider`` : initialise la WS dès qu'une session
 *   authentifiée est disponible, ferme la WS au unmount
 *
 * Doit être placé dans le ``RootLayout`` (server component) entre
 * ``<body>`` et les pages.
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <WebSocketProvider>{children}</WebSocketProvider>
    </SessionProvider>
  );
}
