'use client';

import { useState } from 'react';
import {
  lockRoleDocument,
  regenerateRoleDocument,
  unlockRoleDocument,
} from '@/lib/api/role-documents';
import type { RoleDocument } from '@/lib/types';

interface Props {
  doc: RoleDocument;
  onLockChange: () => void;
  onRegenerated: () => void;
}

export function DocumentActions({ doc, onLockChange, onRegenerated }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggleLock() {
    setBusy(true);
    setError(null);
    try {
      if (doc.locked) {
        await unlockRoleDocument(doc.id);
      } else {
        await lockRoleDocument(doc.id);
      }
      onLockChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur inconnue');
    } finally {
      setBusy(false);
    }
  }

  async function triggerRegen() {
    setBusy(true);
    setError(null);
    try {
      await regenerateRoleDocument(doc.id);
      onRegenerated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur inconnue');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.4rem' }}>
      <div style={{ display: 'flex', gap: '0.4rem' }}>
        <button
          type="button"
          onClick={toggleLock}
          disabled={busy}
          style={{
            padding: '0.3rem 0.7rem',
            background: 'white',
            border: '1px solid #d1d5db',
            borderRadius: 4,
            color: '#374151',
            fontSize: '0.8rem',
            cursor: busy ? 'not-allowed' : 'pointer',
            opacity: busy ? 0.6 : 1,
          }}
        >
          {doc.locked ? 'Déverrouiller' : 'Verrouiller'}
        </button>
        <button
          type="button"
          onClick={triggerRegen}
          disabled={busy || doc.locked}
          title={doc.locked ? 'Déverrouille pour régénérer' : ''}
          style={{
            padding: '0.3rem 0.7rem',
            background: '#7c3aed',
            border: 0,
            borderRadius: 4,
            color: 'white',
            fontSize: '0.8rem',
            fontWeight: 600,
            cursor: busy || doc.locked ? 'not-allowed' : 'pointer',
            opacity: busy || doc.locked ? 0.5 : 1,
          }}
        >
          Régénérer
        </button>
      </div>
      {error && (
        <pre
          style={{
            margin: 0,
            padding: '0.4rem',
            background: '#fef2f2',
            color: '#991b1b',
            fontSize: '0.7rem',
            maxWidth: 280,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {error}
        </pre>
      )}
    </div>
  );
}
