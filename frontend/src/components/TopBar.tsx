'use client';

import { AppsMenu } from './AppsMenu';

/**
 * TopBar globale minimaliste — héberge l'app launcher (menu hamburger)
 * cross-modules à droite. Les pages individuelles conservent leurs propres
 * headers locaux (titre + actions de la page).
 */
export function TopBar() {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: '0.5rem',
        padding: '0.4rem 1rem',
        borderBottom: '1px solid #e5e7eb',
        background: '#fafafa',
        height: 48,
        boxSizing: 'border-box',
      }}
    >
      <AppsMenu />
    </header>
  );
}
