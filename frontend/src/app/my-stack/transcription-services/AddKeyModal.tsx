'use client';

import { useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { createKey } from '@/lib/api/transcription-keys';
import {
  listSecrets,
  SECRET_TYPE_LABELS,
  TRANSCRIPTION_SECRET_TYPES,
} from '@/lib/api/secrets';

interface Props {
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

export function AddKeyModal({ onClose, onSaved }: Props) {
  const { data: secrets, isLoading } = useSWR(['secrets'], () => listSecrets());

  const [secretId, setSecretId] = useState('');
  const [label, setLabel] = useState('');
  const [workersCount, setWorkersCount] = useState(1);
  const [isPrimary, setIsPrimary] = useState(false);
  const [isFallback, setIsFallback] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const transcriptionSecrets = (secrets ?? []).filter((s) =>
    TRANSCRIPTION_SECRET_TYPES.includes(s.secret_type),
  );

  const effectiveSecretId = secretId !== '' ? secretId : transcriptionSecrets[0]?.id ?? '';

  const handleSubmit = async () => {
    if (!effectiveSecretId) {
      setError('Sélectionne un secret');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createKey({
        secret_id: effectiveSecretId,
        label: label || null,
        workers_count: workersCount,
        is_primary: isPrimary,
        is_fallback: isFallback,
      });
      await onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 50,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.5)',
    }}>
      <div style={{ width: '100%', maxWidth: 500, background: 'white', padding: 24, borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.15)', maxHeight: '90vh', overflowY: 'auto' }}>
        <h2 style={{ marginBottom: 16, fontSize: '1.125rem', fontWeight: 600 }}>Ajouter une clé de transcription</h2>

        {isLoading ? (
          <p style={{ color: '#6b7280', fontSize: 14 }}>Chargement des secrets…</p>
        ) : transcriptionSecrets.length === 0 ? (
          <div style={{
            border: '1px solid #fde68a', background: '#fef3c7',
            padding: 16, borderRadius: 4, fontSize: 14, marginBottom: 16,
          }}>
            <strong>Aucun secret de transcription.</strong> Saisissez d&apos;abord une clé dans
            l&apos;onglet{' '}
            <Link href="/my-stack/secrets" style={{ color: '#2563eb' }}>Secrets</Link>.
          </div>
        ) : (
          <>
            <label style={{ display: 'block', marginBottom: 12 }}>
              <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Secret</span>
              <select
                value={effectiveSecretId}
                onChange={(e) => setSecretId(e.target.value)}
                style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4 }}
              >
                {transcriptionSecrets.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label} ({SECRET_TYPE_LABELS[s.secret_type]})
                  </option>
                ))}
              </select>
            </label>

            <label style={{ display: 'block', marginBottom: 12 }}>
              <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Libellé (optionnel)</span>
              <input
                type="text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Ex: Compte perso"
                style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4, boxSizing: 'border-box' }}
              />
            </label>

            <label style={{ display: 'block', marginBottom: 12 }}>
              <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
                Workers (1-5) : {workersCount}
              </span>
              <input
                type="range"
                min={1} max={5} step={1}
                value={workersCount}
                onChange={(e) => setWorkersCount(Number(e.target.value))}
                style={{ width: '100%' }}
              />
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <input type="checkbox" checked={isPrimary} onChange={(e) => setIsPrimary(e.target.checked)} />
              <span>Provider primaire</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <input type="checkbox" checked={isFallback} onChange={(e) => setIsFallback(e.target.checked)} />
              <span>Activer en fallback</span>
            </label>
          </>
        )}

        {error !== null && <p style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</p>}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            type="button"
            onClick={onClose}
            style={{ border: '1px solid #d1d5db', padding: '6px 14px', borderRadius: 4, background: 'white', cursor: 'pointer', fontSize: 13 }}
          >
            Annuler
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={submitting || !effectiveSecretId}
            style={{
              background: '#2563eb', color: 'white', padding: '6px 14px', borderRadius: 4, border: 'none',
              cursor: 'pointer', fontSize: 13,
              opacity: submitting || !effectiveSecretId ? 0.5 : 1,
            }}
          >
            {submitting ? 'Ajout…' : 'Ajouter'}
          </button>
        </div>
      </div>
    </div>
  );
}
