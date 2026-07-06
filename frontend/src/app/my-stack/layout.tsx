'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

const TABS = [
  { href: '/my-stack/wallets', label: 'Coffres (wallets)' },
  { href: '/my-stack/secrets', label: 'Secrets' },
  { href: '/my-stack/social-accounts', label: 'Comptes réseaux sociaux' },
  { href: '/my-stack/transcription-services', label: 'Services de transcription' },
  { href: '/my-stack/quotas', label: 'Quotas et garde-fous' },
];

export default function MyStackLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '1.5rem 1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <Link
          href="/"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            fontSize: '0.875rem',
            color: '#6b7280',
            textDecoration: 'none',
          }}
        >
          ← Retour
        </Link>
        <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700 }}>Ma stack</h1>
      </div>

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
