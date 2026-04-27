'use client';

import { useCallback, useState } from 'react';
import { useParams } from 'next/navigation';
import useSWR from 'swr';
import { listRuns } from '@/lib/api/runs';
import { useWebSocketEvent } from '@/lib/ws/hooks';
import type { Run, WSEventPayload } from '@/lib/types';
import { PipelineStepper } from './PipelineStepper';
import { RunCard } from './RunCard';
import { RunDiff } from './RunDiff';

interface CompareState {
  a: Run;
  b: Run | null;
}

export default function AnalysesPage() {
  const params = useParams();
  const id = params['id'] as string;

  const {
    data: runs,
    error,
    isLoading,
    mutate,
  } = useSWR(['runs', id], () => listRuns(id), {
    refreshInterval: 5000,
  });

  const handleWSEvent = useCallback(
    (_payload: WSEventPayload) => {
      void mutate();
    },
    [mutate],
  );

  useWebSocketEvent('runs_changes', handleWSEvent);

  const [compare, setCompare] = useState<CompareState | null>(null);
  const [selectingB, setSelectingB] = useState(false);

  function handleCompare(run: Run) {
    setCompare({ a: run, b: null });
    setSelectingB(true);
  }

  function handleSelectB(run: Run) {
    if (!compare) return;
    setCompare({ a: compare.a, b: run });
    setSelectingB(false);
  }

  function handleCloseDiff() {
    setCompare(null);
    setSelectingB(false);
  }

  return (
    <main style={{ padding: '2rem', maxWidth: 960, margin: '0 auto' }}>
      <h1>Analyses</h1>
      <p style={{ color: '#666', marginBottom: '1.5rem' }}>
        Déclenchez les étages du pipeline de synthèse et suivez les runs en temps réel.
      </p>

      <PipelineStepper projectId={id} onRunStarted={() => void mutate()} />

      {selectingB && compare && (
        <div
          style={{
            background: '#dbeafe',
            borderRadius: 6,
            padding: '0.75rem 1rem',
            marginBottom: '1rem',
            fontSize: '0.9rem',
            color: '#1d4ed8',
          }}
        >
          Sélectionnez un deuxième run à comparer avec{' '}
          <strong>{compare.a.id.slice(0, 8)}</strong>.{' '}
          <button onClick={handleCloseDiff} style={{ fontSize: '0.85rem' }}>
            Annuler
          </button>
        </div>
      )}

      {isLoading && <p style={{ color: '#666' }}>Chargement des runs…</p>}
      {error && (
        <p style={{ color: '#cf222e' }}>
          Erreur lors du chargement : {error instanceof Error ? error.message : 'Erreur inconnue'}
        </p>
      )}

      {runs && runs.length === 0 && !isLoading && (
        <p style={{ color: '#888' }}>
          Aucun run pour ce projet. Utilisez le pipeline ci-dessus pour démarrer.
        </p>
      )}

      {runs &&
        runs.map((run) => (
          <RunCard
            key={run.id}
            run={run}
            onCompare={
              selectingB && compare && run.id !== compare.a.id
                ? () => handleSelectB(run)
                : !selectingB
                  ? () => handleCompare(run)
                  : undefined
            }
          />
        ))}

      {compare?.b && (
        <RunDiff runA={compare.a} runB={compare.b} onClose={handleCloseDiff} />
      )}
    </main>
  );
}
