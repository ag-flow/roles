'use client';

import { useState } from 'react';
import { disconnect, startOAuth } from '@/lib/api/github';
import type { GithubIntegrationStatus } from '@/lib/types';

interface Props {
  status: GithubIntegrationStatus;
  onChange: () => void;
}

export function ConnectGithubButton({ status, onChange }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connect() {
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

  async function handleDisconnect() {
    setBusy(true);
    setError(null);
    try {
      await disconnect();
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur');
    } finally {
      setBusy(false);
    }
  }

  if (!status.connected) {
    return (
      <div>
        <button
          type="button"
          onClick={connect}
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
          Connecter GitHub
        </button>
        {error && (
          <p style={{ color: '#dc2626', fontSize: '0.8rem', marginTop: '0.5rem' }}>
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <div>
      <p style={{ margin: 0 }}>
        Connecté en tant que <strong>@{status.github_login}</strong>
        {status.scope && ` (scope : ${status.scope})`}
      </p>
      <button
        type="button"
        onClick={handleDisconnect}
        disabled={busy}
        style={{
          marginTop: '0.5rem',
          padding: '0.4rem 0.9rem',
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
      {error && (
        <p style={{ color: '#dc2626', fontSize: '0.8rem', marginTop: '0.5rem' }}>
          {error}
        </p>
      )}
    </div>
  );
}
