'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { listSecrets, deleteSecret, SECRET_TYPE_LABELS } from '@/lib/api/secrets';
import { ApiError } from '@/lib/api/client';
import { StatusIndicator } from '@/components/StatusIndicator';
import type { StatusKind } from '@/components/StatusIndicator';
import { AddSecretModal } from './AddSecretModal';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
}

function extractDetail(e: unknown): string {
  if (e instanceof ApiError) {
    try {
      const parsed: unknown = JSON.parse(e.body);
      if (
        typeof parsed === 'object' &&
        parsed !== null &&
        'detail' in parsed &&
        typeof (parsed as { detail: unknown }).detail === 'string'
      ) {
        return (parsed as { detail: string }).detail;
      }
    } catch {
      // body non-JSON — on retombe sur le message brut
    }
    return e.body;
  }
  return String(e);
}

export default function SecretsPage() {
  const { data, error, isLoading, mutate } = useSWR(['secrets'], () => listSecrets());
  const [modalOpen, setModalOpen] = useState(false);

  const handleDelete = async (id: string) => {
    if (!window.confirm('Supprimer ce secret ?')) return;
    try {
      await deleteSecret(id);
      await mutate();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        window.alert(extractDetail(e));
      } else {
        window.alert('Erreur : ' + String(e));
      }
    }
  };

  if (error) return <p style={{ color: '#dc2626' }}>Erreur de chargement.</p>;
  if (isLoading) return <p style={{ color: '#6b7280' }}>Chargement…</p>;

  const secrets = data ?? [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, margin: 0 }}>Secrets</h2>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          style={{
            background: '#2563eb', color: 'white', padding: '6px 12px',
            borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 14,
          }}
        >
          + Ajouter un secret
        </button>
      </div>

      {secrets.length === 0 ? (
        <div style={{
          border: '1px solid #bfdbfe', background: '#eff6ff',
          padding: 16, borderRadius: 4, fontSize: 14, color: '#1e3a8a',
        }}>
          <strong>Aucun secret.</strong> Ajoutez ici vos clés API de transcription et vos
          cookies de réseaux sociaux, puis référencez-les depuis les onglets Services et Comptes.
        </div>
      ) : (
        <ul
          style={{
            listStyle: 'none',
            margin: 0,
            padding: 0,
            border: '1px solid #e5e7eb',
            borderRadius: 6,
          }}
        >
          {secrets.map((s, idx) => (
            <li
              key={s.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                borderTop: idx === 0 ? 'none' : '1px solid #e5e7eb',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 500, fontSize: '0.9rem' }}>{s.label}</span>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: 600,
                      padding: '2px 8px',
                      borderRadius: 9999,
                      backgroundColor: s.storage === 'wallet' ? '#eff6ff' : '#f3f4f6',
                      color: s.storage === 'wallet' ? '#1d4ed8' : '#4b5563',
                      border: s.storage === 'wallet' ? '1px solid #bfdbfe' : '1px solid #e5e7eb',
                    }}
                  >
                    {s.storage === 'wallet' ? 'Wallet' : 'Local (chiffré)'}
                  </span>
                </div>
                <div
                  style={{
                    marginTop: 4,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    fontSize: '0.75rem',
                    color: '#6b7280',
                  }}
                >
                  <StatusIndicator status={s.status as StatusKind} size="sm" />
                  <span>{SECRET_TYPE_LABELS[s.secret_type]}</span>
                  <span>Ajouté : {formatDate(s.created_at)}</span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => void handleDelete(s.id)}
                style={{
                  padding: '0.25rem 0.75rem',
                  fontSize: '0.875rem',
                  border: '1px solid #fca5a5',
                  borderRadius: 4,
                  background: '#fff',
                  color: '#dc2626',
                  cursor: 'pointer',
                }}
              >
                Supprimer
              </button>
            </li>
          ))}
        </ul>
      )}

      {modalOpen && (
        <AddSecretModal
          onClose={() => setModalOpen(false)}
          onSaved={async () => {
            setModalOpen(false);
            await mutate();
          }}
        />
      )}
    </div>
  );
}
