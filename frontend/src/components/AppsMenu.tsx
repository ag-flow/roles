'use client';

import { useEffect, useRef, useState } from 'react';
import useSWR from 'swr';
import { getApps } from '@/lib/api/apps';
import type { AppEntry } from '@/lib/types';

/**
 * Menu hamburger (app launcher) listant les autres apps de la suite agflow.
 * Caché si :
 *  - chargement initial en cours (évite flash sur écran)
 *  - liste vide ou erreur (le backend renvoie [] si apps.json absent/invalide)
 *
 * Source : `GET /api/admin/apps` (lit `apps.json` bind-monté côté backend).
 */
export function AppsMenu() {
  const { data, isLoading } = useSWR(
    'apps-menu',
    getApps,
    {
      revalidateOnFocus: false,
      dedupingInterval: 5 * 60 * 1000, // 5 min — équivalent staleTime TanStack
    },
  );
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  // Fermer au clic extérieur / Escape
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const urls = data?.urls ?? [];
  if (isLoading || urls.length === 0) return null;

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        type="button"
        aria-label="Apps"
        title="Apps"
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 36,
          height: 36,
          padding: 0,
          background: 'transparent',
          border: '1px solid transparent',
          borderRadius: 6,
          color: '#374151',
          cursor: 'pointer',
        }}
      >
        {/* Icône grille 3x3 (équivalent lucide Grid3x3) */}
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <rect x="3" y="3" width="7" height="7" />
          <rect x="14" y="3" width="7" height="7" />
          <rect x="3" y="14" width="7" height="7" />
          <rect x="14" y="14" width="7" height="7" />
        </svg>
      </button>

      {open && (
        <ul
          role="menu"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            right: 0,
            minWidth: 220,
            margin: 0,
            padding: '0.4rem 0',
            background: 'white',
            border: '1px solid #d1d5db',
            borderRadius: 6,
            boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
            listStyle: 'none',
            zIndex: 100,
          }}
        >
          {urls.map((app) => (
            <AppsMenuItem key={app.key} app={app} onSelect={() => setOpen(false)} />
          ))}
        </ul>
      )}
    </div>
  );
}

function AppsMenuItem({
  app,
  onSelect,
}: {
  app: AppEntry;
  onSelect: () => void;
}) {
  const [iconOk, setIconOk] = useState(true);
  return (
    <li role="none">
      <a
        role="menuitem"
        href={app.url}
        target="_blank"
        rel="noopener noreferrer"
        onClick={onSelect}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.6rem',
          padding: '0.45rem 0.8rem',
          color: '#111827',
          textDecoration: 'none',
          fontSize: '0.9rem',
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLAnchorElement).style.background = '#f3f4f6';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLAnchorElement).style.background = 'transparent';
        }}
      >
        {iconOk ? (
          // eslint-disable-next-line @next/next/no-img-element -- favicon externe, next/image overkill
          <img
            src={app.icon}
            alt=""
            width={18}
            height={18}
            onError={() => setIconOk(false)}
            style={{ borderRadius: 3, flex: '0 0 auto' }}
          />
        ) : (
          <span
            aria-hidden="true"
            style={{
              display: 'inline-block',
              width: 18,
              height: 18,
              borderRadius: 3,
              background: '#e5e7eb',
              flex: '0 0 auto',
            }}
          />
        )}
        <span>{app.label}</span>
      </a>
    </li>
  );
}
