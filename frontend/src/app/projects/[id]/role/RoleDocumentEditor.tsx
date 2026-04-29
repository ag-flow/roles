'use client';

import { useState } from 'react';
import type { RoleDocumentSummary } from '@/lib/types';
import { DocumentTree } from './DocumentTree';
import { DocumentDetail } from './DocumentDetail';

interface Props {
  projectId: string;
  sections: Record<string, RoleDocumentSummary[]>;
  onChange: () => void;
}

export function RoleDocumentEditor({ projectId, sections, onChange }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

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
    <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start' }}>
      <DocumentTree
        sections={sections}
        selectedId={selectedId}
        onSelect={setSelectedId}
      />
      <main style={{ flex: 1, minWidth: 0 }}>
        {selectedId ? (
          <DocumentDetail
            docId={selectedId}
            projectId={projectId}
            onChange={onChange}
          />
        ) : (
          <p style={{ color: '#9ca3af' }}>Sélectionnez un document à gauche.</p>
        )}
      </main>
    </div>
  );
}
