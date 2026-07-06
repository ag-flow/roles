'use client';

import { useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { createCredential } from '@/lib/api/credentials';
import { listSecrets, SECRET_TYPE_LABELS } from '@/lib/api/secrets';
import type { SecretType } from '@/lib/api/secrets';
import type { CredentialPlatform } from '@/lib/types';

interface Props {
  platform: CredentialPlatform;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

const LABELS: Record<CredentialPlatform, string> = {
  youtube: 'YouTube',
  instagram: 'Instagram',
  tiktok: 'TikTok',
};

export function AddAccountModal({ platform, onClose, onSaved }: Props) {
  const cookiesType = `${platform}-cookies` as SecretType;
  const { data: secrets, isLoading } = useSWR(['secrets'], () => listSecrets());

  const [label, setLabel] = useState('');
  const [secretId, setSecretId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cookiesSecrets = (secrets ?? []).filter((s) => s.secret_type === cookiesType);
  const effectiveSecretId = secretId !== '' ? secretId : cookiesSecrets[0]?.id ?? '';

  const handleSubmit = async () => {
    if (!effectiveSecretId) {
      setError('Sélectionne un secret de cookies');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createCredential({
        secret_id: effectiveSecretId,
        label: label.trim() !== '' ? label.trim() : null,
      });
      await onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(0,0,0,0.5)',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 512,
          borderRadius: 8,
          backgroundColor: '#fff',
          padding: '1.5rem',
          boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
        }}
      >
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.125rem', fontWeight: 600 }}>
          Ajouter un compte {LABELS[platform]}
        </h2>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span
            style={{ display: 'block', marginBottom: 4, fontSize: '0.875rem', fontWeight: 500 }}
          >
            Libellé (optionnel)
          </span>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Ex : Compte perso"
            style={{
              width: '100%',
              boxSizing: 'border-box',
              border: '1px solid #d1d5db',
              borderRadius: 4,
              padding: '0.5rem 0.75rem',
              fontSize: '0.875rem',
            }}
          />
        </label>

        {isLoading ? (
          <p style={{ color: '#6b7280', fontSize: '0.875rem' }}>Chargement des secrets…</p>
        ) : cookiesSecrets.length === 0 ? (
          <div
            style={{
              border: '1px solid #fde68a',
              background: '#fef3c7',
              padding: 16,
              borderRadius: 4,
              fontSize: '0.875rem',
            }}
          >
            <strong>Aucun secret « {SECRET_TYPE_LABELS[cookiesType]} ».</strong> Déposez
            d&apos;abord votre fichier cookies.txt dans l&apos;onglet{' '}
            <Link href="/my-stack/secrets" style={{ color: '#2563eb' }}>Secrets</Link>.
          </div>
        ) : (
          <label style={{ display: 'block', marginBottom: 4 }}>
            <span
              style={{ display: 'block', marginBottom: 4, fontSize: '0.875rem', fontWeight: 500 }}
            >
              Secret (cookies)
            </span>
            <select
              value={effectiveSecretId}
              onChange={(e) => setSecretId(e.target.value)}
              style={{
                width: '100%',
                border: '1px solid #d1d5db',
                borderRadius: 4,
                padding: '0.5rem 0.75rem',
                fontSize: '0.875rem',
              }}
            >
              {cookiesSecrets.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label} ({SECRET_TYPE_LABELS[s.secret_type]})
                </option>
              ))}
            </select>
          </label>
        )}

        {error !== null && (
          <p style={{ marginTop: 12, fontSize: '0.875rem', color: '#dc2626' }}>{error}</p>
        )}

        <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '0.5rem 1rem',
              fontSize: '0.875rem',
              border: '1px solid #d1d5db',
              borderRadius: 4,
              background: '#fff',
              cursor: 'pointer',
            }}
          >
            Annuler
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={submitting || effectiveSecretId === ''}
            style={{
              padding: '0.5rem 1rem',
              fontSize: '0.875rem',
              borderRadius: 4,
              border: 'none',
              backgroundColor: submitting || effectiveSecretId === '' ? '#93c5fd' : '#2563eb',
              color: '#fff',
              cursor: submitting || effectiveSecretId === '' ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? 'Ajout…' : 'Ajouter'}
          </button>
        </div>
      </div>
    </div>
  );
}
