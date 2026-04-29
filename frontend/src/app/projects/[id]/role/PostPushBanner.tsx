'use client';

import type { PushToAgflowResponse } from '@/lib/types';

interface Props {
  projectId: string;
  result: PushToAgflowResponse;
  partialFailure: 'prompt' | null;
  onDismiss: () => void;
}

/**
 * Stub D1.4 — implémentation complète (retry generate-prompts) en D1.5.
 */
export function PostPushBanner({ result, partialFailure, onDismiss }: Props) {
  const isError = partialFailure !== null;
  return (
    <div
      role="status"
      style={{
        marginTop: '1rem',
        padding: '0.75rem 1rem',
        borderRadius: 6,
        borderLeft: `4px solid ${isError ? '#dc2626' : '#16a34a'}`,
        background: isError ? '#fef2f2' : '#f0fdf4',
        color: isError ? '#991b1b' : '#14532d',
      }}
    >
      <strong>
        {isError
          ? 'Rôle uploadé sur ag.flow, mais la génération du prompt a échoué'
          : 'Rôle poussé sur ag.flow ✓'}
      </strong>
      <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem' }}>
        {result.documents_count ?? 0} document(s),{' '}
        {Math.round(result.zip_size_bytes / 1024)} Ko.
      </p>
      <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
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
            border: '1px solid currentColor',
            borderRadius: 4,
            color: 'inherit',
            cursor: 'pointer',
          }}
        >
          Fermer
        </button>
      </div>
    </div>
  );
}
