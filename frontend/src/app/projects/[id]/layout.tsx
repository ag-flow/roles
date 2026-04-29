'use client';

import Link from 'next/link';
import { useParams, usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

const TABS = [
  { suffix: 'sources', label: 'Sources' },
  { suffix: 'corpus', label: 'Corpus' },
  { suffix: 'prompts', label: 'Prompts' },
  { suffix: 'analyses', label: 'Analyses' },
  { suffix: 'role', label: 'Rôle' },
];

export default function ProjectLayout({ children }: { children: ReactNode }) {
  const params = useParams();
  const pathname = usePathname();
  const projectId = params['id'] as string;

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '1.5rem 1rem' }}>
      <nav
        style={{
          display: 'flex',
          borderBottom: '1px solid #e5e7eb',
          marginBottom: '1.5rem',
          gap: 0,
        }}
      >
        {TABS.map((tab) => {
          const href = `/projects/${projectId}/${tab.suffix}`;
          const isActive = pathname.startsWith(href);
          return (
            <Link
              key={tab.suffix}
              href={href}
              style={{
                padding: '0.5rem 1rem',
                fontSize: '0.875rem',
                textDecoration: 'none',
                borderBottom: isActive
                  ? '2px solid #2563eb'
                  : '2px solid transparent',
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
