'use client';

import { useEffect, useState } from 'react';
import { useWebSocketEvent } from '@/lib/ws/hooks';
import type { PushEventPayload, PushStep } from '@/lib/types';

const STEP_LABELS: Record<PushStep, string> = {
  zip_built: 'Construction du ZIP',
  role_ready: 'Création du rôle ag.flow',
  zip_uploaded: 'Upload du ZIP',
  prompts_generated: 'Génération du prompt orchestrateur',
  done: 'Terminé',
  failed: 'Échec',
};

const STEP_ORDER: readonly PushStep[] = [
  'zip_built',
  'role_ready',
  'zip_uploaded',
  'prompts_generated',
] as const;

interface ProgressState {
  steps: PushStep[];
  finalStatus: 'done' | 'failed' | null;
  errorDetail: string | null;
}

/**
 * Hook qui collecte les événements `agflow_push_events` du tenant courant
 * pour un projet donné, tant que `active=true`. Renvoie les étapes reçues
 * dans l'ordre et le statut final éventuel.
 */
export function usePushProgress(
  projectId: string,
  active: boolean,
): ProgressState {
  const [state, setState] = useState<ProgressState>({
    steps: [],
    finalStatus: null,
    errorDetail: null,
  });

  useWebSocketEvent('agflow_push_events', (payload: PushEventPayload) => {
    if (!active) return;
    if (payload.project_id !== projectId) return;
    setState((prev) => {
      const next: ProgressState = {
        steps: prev.steps.includes(payload.step)
          ? prev.steps
          : [...prev.steps, payload.step],
        finalStatus:
          payload.status === 'done'
            ? 'done'
            : payload.status === 'failed'
              ? 'failed'
              : prev.finalStatus,
        errorDetail:
          payload.status === 'failed' && payload.detail?.['error']
            ? String(payload.detail['error'])
            : prev.errorDetail,
      };
      return next;
    });
  });

  // Reset quand on (ré)active la dialog (nouveau push)
  useEffect(() => {
    if (active) {
      setState({ steps: [], finalStatus: null, errorDetail: null });
    }
  }, [active]);

  return state;
}

interface Props {
  steps: PushStep[];
  finalStatus: 'done' | 'failed' | null;
  errorDetail: string | null;
  onClose: () => void;
}

export function PushProgressDialog({
  steps,
  finalStatus,
  errorDetail,
  onClose,
}: Props) {
  const reachedFailure = finalStatus === 'failed';
  return (
    <div
      role="dialog"
      aria-label="Progression du push"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
      }}
    >
      <div
        style={{
          background: 'white',
          padding: '1.5rem 2rem',
          borderRadius: 8,
          minWidth: 420,
          maxWidth: 560,
        }}
      >
        <h3 style={{ margin: '0 0 1rem', fontSize: '1.125rem', fontWeight: 600 }}>
          {finalStatus === 'done'
            ? 'Push terminé ✓'
            : reachedFailure
              ? 'Push échoué'
              : 'Push en cours…'}
        </h3>
        <ol style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {STEP_ORDER.map((step) => {
            const reached = steps.includes(step);
            return (
              <li
                key={step}
                style={{
                  padding: '0.25rem 0',
                  color: reached ? '#15803d' : '#9ca3af',
                }}
              >
                {reached ? '✓' : '◯'} {STEP_LABELS[step]}
              </li>
            );
          })}
        </ol>
        {reachedFailure && errorDetail && (
          <pre
            style={{
              marginTop: '1rem',
              padding: '0.5rem',
              background: '#fef2f2',
              border: '1px solid #fca5a5',
              color: '#991b1b',
              fontSize: '0.75rem',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {errorDetail}
          </pre>
        )}
        {finalStatus !== null && (
          <div style={{ marginTop: '1rem', textAlign: 'right' }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '0.4rem 0.9rem',
                border: '1px solid #d1d5db',
                borderRadius: 4,
                background: 'white',
                cursor: 'pointer',
              }}
            >
              Fermer
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
