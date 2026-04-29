'use client';

import { useState } from 'react';
import useSWR from 'swr';
import {
  getRoleDocument,
  listRoleDocumentVersions,
  setCurrentRoleDocument,
} from '@/lib/api/role-documents';
import { DocumentEditor } from './DocumentEditor';
import { DocumentActions } from './DocumentActions';
import { VersionList } from './VersionList';
import { VersionDiff } from './VersionDiff';

interface Props {
  docId: string;
  projectId: string;
  onChange: () => void;
}

export function DocumentDetail({ docId, onChange }: Props) {
  const doc = useSWR(['role-document', docId], () => getRoleDocument(docId));
  const versions = useSWR(['role-document-versions', docId], () =>
    listRoleDocumentVersions(docId),
  );
  const [diffWith, setDiffWith] = useState<string | null>(null);

  if (doc.isLoading || versions.isLoading) {
    return <p>Chargement…</p>;
  }
  if (doc.error || !doc.data || versions.error || !versions.data) {
    return (
      <p style={{ color: '#dc2626' }}>Erreur de chargement du document.</p>
    );
  }

  async function promote(versionId: string) {
    await setCurrentRoleDocument(versionId);
    await Promise.all([doc.mutate(), versions.mutate()]);
    onChange();
  }

  return (
    <article style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <header
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            marginBottom: '0.75rem',
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: '1.25rem' }}>{doc.data.name}</h2>
            <small style={{ color: '#6b7280' }}>
              {doc.data.section} · v{doc.data.version}
              {doc.data.is_current && ' · current'}
              {doc.data.locked && ' · 🔒 verrouillé'}
            </small>
          </div>
          <DocumentActions
            doc={doc.data}
            onLockChange={() => doc.mutate()}
            onRegenerated={() => {
              doc.mutate();
              versions.mutate();
              onChange();
            }}
          />
        </header>
        <DocumentEditor
          doc={doc.data}
          onSaved={() => {
            doc.mutate();
            versions.mutate();
            onChange();
          }}
        />
        {diffWith && (
          <VersionDiff
            currentContent={doc.data.content}
            currentVersion={doc.data.version}
            otherDocId={diffWith}
            onClose={() => setDiffWith(null)}
          />
        )}
      </div>
      <VersionList
        versions={versions.data}
        onPromote={promote}
        onShowDiff={setDiffWith}
      />
    </article>
  );
}
