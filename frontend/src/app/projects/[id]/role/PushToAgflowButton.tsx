'use client';

import type { PushPreview } from '@/lib/types';

interface Props {
  projectId: string;
  preview: PushPreview;
  onPushed: () => void;
}

/**
 * Stub D1.2 — implémentation complète en D1.4.
 */
export function PushToAgflowButton(_props: Props) {
  const label = _props.preview.target_role_id
    ? 'Mettre à jour ag.flow'
    : 'Pousser vers ag.flow';
  return (
    <button
      type="button"
      disabled
      style={{
        padding: '0.5rem 1rem',
        background: '#2563eb',
        color: 'white',
        border: 0,
        borderRadius: 4,
        opacity: 0.5,
        cursor: 'not-allowed',
      }}
      title="Bouton encore en cours d'implémentation (D1.4)"
    >
      {label}
    </button>
  );
}
