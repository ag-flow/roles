'use client';

import { useState } from 'react';
import { generatePromptsOnAgflow } from '@/lib/api/agflow-export';
import type { PushToAgflowResponse } from '@/lib/types';

interface Props {
  projectId: string;
  result: PushToAgflowResponse;
  /**
   * `'prompt'` = le ZIP est uploadé mais la génération du prompt orchestrateur
   * a échoué. Banner rouge + bouton retry. `null` = succès complet.
   */
  partialFailure: 'prompt' | null;
  onDismiss: () => void;
}

export function PostPushBanner({
  projectId,
  result,
  partialFailure,
  onDismiss,
}: Props) {
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  if (partialFailure === 'prompt') {
    async function retry() {
      setRetrying(true);
      setRetryError(null);
      try {
        await generatePromptsOnAgflow(projectId);
        onDismiss();
      } catch (err) {
        setRetryError(err instanceof Error ? err.message : 'Erreur inconnue');
      } finally {
        setRetrying(false);
      }
    }

    return (
      <div
        role="status"
        style={{
          marginTop: '1rem',
          padding: '0.75rem 1rem',
          borderRadius: 6,
          borderLeft: '4px solid #dc2626',
          background: '#fef2f2',
          color: '#991b1b',
        }}
      >
        <strong>
          ⚠ Rôle uploadé sur ag.flow, mais la génération du prompt a échoué
        </strong>
        <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem' }}>
          Le rôle est bien créé mais son prompt orchestrateur n&apos;a pas été
          généré. Vous pouvez réessayer ; sinon, vous pourrez le générer plus
          tard depuis l&apos;admin ag.flow.
        </p>
        <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem' }}>
          <a
            href={result.agflow_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Voir dans l&apos;admin ag.flow →
          </a>
        </p>
        {retryError && (
          <pre
            style={{
              marginTop: '0.5rem',
              padding: '0.5rem',
              background: '#fee2e2',
              fontSize: '0.75rem',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {retryError}
          </pre>
        )}
        <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
          <button
            type="button"
            onClick={retry}
            disabled={retrying}
            style={{
              padding: '0.4rem 0.9rem',
              background: '#dc2626',
              color: 'white',
              border: 0,
              borderRadius: 4,
              cursor: retrying ? 'not-allowed' : 'pointer',
              opacity: retrying ? 0.6 : 1,
              fontSize: '0.875rem',
              fontWeight: 600,
            }}
          >
            {retrying ? 'Réessai…' : 'Réessayer la génération du prompt'}
          </button>
          <button
            type="button"
            onClick={onDismiss}
            style={{
              padding: '0.4rem 0.9rem',
              background: 'white',
              border: '1px solid #fca5a5',
              borderRadius: 4,
              color: '#991b1b',
              cursor: 'pointer',
              fontSize: '0.875rem',
            }}
          >
            Plus tard
          </button>
        </div>
      </div>
    );
  }

  // Succès complet
  return (
    <div
      role="status"
      style={{
        marginTop: '1rem',
        padding: '0.75rem 1rem',
        borderRadius: 6,
        borderLeft: '4px solid #16a34a',
        background: '#f0fdf4',
        color: '#14532d',
      }}
    >
      <strong>✓ Rôle poussé sur ag.flow</strong>
      <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem' }}>
        {result.documents_count ?? 0} document(s),{' '}
        {Math.round(result.zip_size_bytes / 1024)} Ko.
        {result.prompt_generated && ' Prompt orchestrateur généré.'}
      </p>
      <div
        style={{
          marginTop: '0.5rem',
          display: 'flex',
          gap: '0.5rem',
          alignItems: 'center',
        }}
      >
        <a
          href={result.agflow_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: '0.875rem' }}
        >
          Voir dans l&apos;admin ag.flow →
        </a>
        <button
          type="button"
          onClick={onDismiss}
          style={{
            marginLeft: 'auto',
            padding: '0.3rem 0.7rem',
            fontSize: '0.8rem',
            background: 'transparent',
            border: '1px solid #16a34a',
            borderRadius: 4,
            color: '#14532d',
            cursor: 'pointer',
          }}
        >
          Fermer
        </button>
      </div>
    </div>
  );
}
