'use client';

import useSWR from 'swr';
import { getRoleDocument } from '@/lib/api/role-documents';

interface Props {
  docId: string;
  projectId: string;
  onChange: () => void;
}

/**
 * Stub D2.1 — implémentation complète (versions, edit, lock, regen, diff)
 * en D2.2-D2.5.
 */
export function DocumentDetail({ docId }: Props) {
  const { data, isLoading, error } = useSWR(
    ['role-document', docId],
    () => getRoleDocument(docId),
  );
  if (isLoading) return <p>Chargement…</p>;
  if (error || !data) return <p style={{ color: '#dc2626' }}>Erreur de chargement</p>;
  return (
    <article>
      <header style={{ marginBottom: '0.75rem' }}>
        <h2 style={{ margin: 0, fontSize: '1.25rem' }}>{data.name}</h2>
        <small style={{ color: '#6b7280' }}>
          {data.section} · v{data.version}
          {data.is_current && ' · current'}
          {data.locked && ' · 🔒 verrouillé'}
        </small>
      </header>
      <pre
        style={{
          padding: '1rem',
          background: '#f9fafb',
          border: '1px solid #e5e7eb',
          borderRadius: 6,
          fontSize: '0.875rem',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          margin: 0,
        }}
      >
        {data.content}
      </pre>
    </article>
  );
}
