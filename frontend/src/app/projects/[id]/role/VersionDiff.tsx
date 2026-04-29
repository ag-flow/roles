'use client';

import type { FC } from 'react';
import useSWR from 'swr';
import ReactDiffViewerImport from 'react-diff-viewer-continued';
import { getRoleDocument } from '@/lib/api/role-documents';

// Le package est typé comme une class component (typages legacy React 17),
// ce qui pose problème avec les types stricts React 18. On le ré-encapsule en
// FunctionComponent typée minimaliste — les props utilisées sont stables.
interface ReactDiffViewerLikeProps {
  oldValue: string;
  newValue: string;
  splitView?: boolean;
  leftTitle?: string;
  rightTitle?: string;
}
const ReactDiffViewer = ReactDiffViewerImport as unknown as FC<ReactDiffViewerLikeProps>;

interface Props {
  currentContent: string;
  currentVersion: number;
  otherDocId: string;
  onClose: () => void;
}

export function VersionDiff({
  currentContent,
  currentVersion,
  otherDocId,
  onClose,
}: Props) {
  const other = useSWR(['role-document-diff', otherDocId], () =>
    getRoleDocument(otherDocId),
  );

  return (
    <div
      role="dialog"
      aria-label="Diff entre versions"
      style={{
        marginTop: '1rem',
        padding: '1rem',
        background: 'white',
        border: '1px solid #d1d5db',
        borderRadius: 6,
        boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '0.75rem',
        }}
      >
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>
          {other.data
            ? `Diff : v${other.data.version} → v${currentVersion} (current)`
            : 'Diff'}
        </h3>
        <button
          type="button"
          onClick={onClose}
          style={{
            padding: '0.3rem 0.7rem',
            background: 'white',
            border: '1px solid #d1d5db',
            borderRadius: 4,
            color: '#374151',
            fontSize: '0.8rem',
            cursor: 'pointer',
          }}
        >
          Fermer
        </button>
      </header>

      {other.isLoading || !other.data ? (
        <p style={{ color: '#6b7280', margin: 0 }}>Chargement…</p>
      ) : (
        <div style={{ fontSize: '0.85rem' }}>
          <ReactDiffViewer
            oldValue={other.data.content}
            newValue={currentContent}
            splitView={true}
            leftTitle={`v${other.data.version}`}
            rightTitle={`v${currentVersion} (current)`}
          />
        </div>
      )}
    </div>
  );
}
