'use client';

import type { RoleDocumentSummary } from '@/lib/types';

interface Props {
  projectId: string;
  sections: Record<string, RoleDocumentSummary[]>;
  onChange: () => void;
}

/**
 * Stub D1.2 — implémentation complète en D2.1+.
 */
export function RoleDocumentEditor({ sections }: Props) {
  const sectionNames = Object.keys(sections);
  if (sectionNames.length === 0) {
    return (
      <p style={{ color: '#6b7280' }}>
        Aucun document généré pour l&apos;instant. Lance le pipeline depuis l&apos;onglet
        Analyses.
      </p>
    );
  }
  return (
    <div style={{ color: '#6b7280', fontStyle: 'italic' }}>
      <p>
        Éditeur en cours d&apos;implémentation (D2). En attendant, voici les sections
        détectées :
      </p>
      <ul>
        {sectionNames.map((s) => (
          <li key={s}>
            <strong>{s}</strong> — {sections[s]?.length ?? 0} document(s)
          </li>
        ))}
      </ul>
    </div>
  );
}
