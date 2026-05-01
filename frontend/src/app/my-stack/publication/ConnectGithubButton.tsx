'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { deleteIntegration, listIntegrations, startOAuth } from '@/lib/api/github';
import type { GithubIntegrationItem } from '@/lib/types';

interface Props {
  onChange?: () => void;
}

export function ConnectGithubButton({ onChange }: Props) {
  const { data: integrations, mutate, isLoading } = useSWR<GithubIntegrationItem[]>(
    'github-integrations',
    listIntegrations,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function addAccount() {
    setBusy(true);
    setError(null);
    try {
      const { redirect_url } = await startOAuth();
      window.location.assign(redirect_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur');
      setBusy(false);
    }
  }

  async function removeOne(id: string) {
    setBusy(true);
    setError(null);
    try {
      await deleteIntegration(id);
      await mutate();
      onChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur');
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) {
    return <p style={{ color: '#6b7280' }}>Chargement…</p>;
  }

  const list = integrations ?? [];

  return (
    <div>
      {list.length === 0 ? (
        <p style={{ color: '#6b7280', margin: '0 0 0.5rem 0' }}>
          Aucun compte GitHub connecté.
        </p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 0.75rem 0' }}>
          {list.map((it) => (
            <li
              key={it.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '0.5rem 0.75rem',
                marginBottom: '0.4rem',
                border: '1px solid #d1d5db',
                borderRadius: 4,
              }}
            >
              <span style={{ flex: 1 }}>
                <strong>@{it.github_login}</strong>
                <span style={{ color: '#6b7280', fontSize: '0.85rem' }}>
                  {' '}— scope : {it.scope}
                </span>
              </span>
              <button
                type="button"
                onClick={() => removeOne(it.id)}
                disabled={busy}
                style={{
                  padding: '0.3rem 0.7rem',
                  background: 'white',
                  color: '#dc2626',
                  border: '1px solid #dc2626',
                  borderRadius: 4,
                  cursor: busy ? 'not-allowed' : 'pointer',
                  fontSize: '0.8rem',
                }}
              >
                Déconnecter
              </button>
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={addAccount}
        disabled={busy}
        style={{
          padding: '0.5rem 1rem',
          background: '#24292f',
          color: 'white',
          border: 0,
          borderRadius: 4,
          cursor: busy ? 'not-allowed' : 'pointer',
          opacity: busy ? 0.6 : 1,
          fontSize: '0.875rem',
          fontWeight: 600,
        }}
      >
        {list.length === 0 ? 'Connecter GitHub' : 'Ajouter un compte'}
      </button>

      {error && (
        <p style={{ color: '#dc2626', fontSize: '0.8rem', marginTop: '0.5rem' }}>
          {error}
        </p>
      )}
    </div>
  );
}
