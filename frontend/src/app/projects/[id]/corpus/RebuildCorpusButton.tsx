'use client';

import { useState } from 'react';
import { rebuildCorpus } from '@/lib/api/corpus';

interface Props {
  projectId: string;
}

export function RebuildCorpusButton({ projectId }: Props) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{
    deleted_chunks: number;
    enqueued_jobs: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onClick() {
    const ok = window.confirm(
      'Reconstruire le corpus va supprimer tous les chunks indexés du projet. ' +
        'Le worker re-traitera ensuite chaque transcript. Continuer ?',
    );
    if (!ok) return;

    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await rebuildCorpus(projectId);
      setResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: '1rem' }}>
      <button
        type="button"
        onClick={onClick}
        disabled={busy}
        style={{
          padding: '0.4rem 0.9rem',
          background: 'white',
          color: '#dc2626',
          border: '1px solid #dc2626',
          borderRadius: 4,
          cursor: busy ? 'not-allowed' : 'pointer',
          fontSize: '0.85rem',
        }}
      >
        {busy ? 'En cours…' : 'Reconstruire le corpus'}
      </button>
      {result && (
        <p
          style={{
            marginTop: '0.5rem',
            color: '#15803d',
            fontSize: '0.85rem',
          }}
        >
          ✓ {result.deleted_chunks} chunk(s) supprimé(s),{' '}
          {result.enqueued_jobs} job(s) re-mis en file. Le worker va re-indexer.
        </p>
      )}
      {error && (
        <p style={{ marginTop: '0.5rem', color: '#dc2626', fontSize: '0.85rem' }}>
          {error}
        </p>
      )}
    </div>
  );
}
