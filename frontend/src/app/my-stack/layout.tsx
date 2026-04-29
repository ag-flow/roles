'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

const TABS = [
  { href: '/my-stack/social-accounts', label: 'Comptes réseaux sociaux' },
  { href: '/my-stack/transcription-services', label: 'Services de transcription' },
  { href: '/my-stack/mistral-config', label: 'Mistral pour la synthèse' },
  { href: '/my-stack/publication', label: 'Publication GitHub' },
  { href: '/my-stack/quotas', label: 'Quotas et garde-fous' },
];

export default function MyStackLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '1.5rem 1rem' }}>
      <h1 style={{ marginBottom: '1.5rem', fontSize: '1.5rem', fontWeight: 700 }}>
        Ma stack
      </h1>

      <nav
        style={{
          display: 'flex',
          borderBottom: '1px solid #e5e7eb',
          marginBottom: '1.5rem',
          gap: 0,
        }}
      >
        {TABS.map((tab) => {
          const isActive = pathname.startsWith(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              style={{
                padding: '0.5rem 1rem',
                fontSize: '0.875rem',
                textDecoration: 'none',
                borderBottom: isActive ? '2px solid #2563eb' : '2px solid transparent',
                marginBottom: -1,
                color: isActive ? '#2563eb' : '#4b5563',
                fontWeight: isActive ? 600 : 400,
                transition: 'color 0.15s',
                whiteSpace: 'nowrap',
              }}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
