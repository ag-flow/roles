'use client';

import type { RoleDocument } from '@/lib/types';

interface Props {
  doc: RoleDocument;
  onSaved: () => void;
}

/**
 * Stub D2.2 — implémentation complète (édition manuelle textarea + save)
 * en D2.3.
 */
export function DocumentEditor({ doc }: Props) {
  return (
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
      {doc.content}
    </pre>
  );
}
