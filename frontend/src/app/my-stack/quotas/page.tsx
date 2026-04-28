'use client';

import useSWR from 'swr';
import { listKeys } from '@/lib/api/transcription-keys';
import { QuotaForm } from './QuotaForm';

export default function QuotasPage() {
  const {
    data,
    error,
    isLoading,
    mutate,
  } = useSWR(['transcription-keys'], () => listKeys());

  if (error !== undefined && error !== null) {
    return <p style={{ color: '#dc2626' }}>Erreur de chargement.</p>;
  }
  if (isLoading) {
    return <p>Chargement…</p>;
  }

  const keys = data ?? [];

  if (keys.length === 0) {
    return (
      <p style={{ fontSize: 14 }}>
        Aucune clé configurée. Configure d&apos;abord une clé dans &quot;Services de
        transcription&quot;.
      </p>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <p style={{ color: '#6b7280', fontSize: 14 }}>
        Définis un cap mensuel par clé. Le suivi du spend est mis à jour à chaque transcription
        et reset automatiquement le 1er du mois.
      </p>
      {keys.map((k) => (
        <QuotaForm key={k.id} keyData={k} onSaved={() => void mutate()} />
      ))}
    </div>
  );
}
