'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { listCredentials, deleteCredential, testCredential } from '@/lib/api/credentials';
import type { CredentialPlatform, UserCredential } from '@/lib/types';
import { AccountsList } from './AccountsList';
import { AddAccountModal } from './AddAccountModal';

const PLATFORMS: { value: CredentialPlatform; label: string }[] = [
  { value: 'youtube', label: 'YouTube' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'tiktok', label: 'TikTok' },
];

export default function SocialAccountsPage() {
  const { data, error, isLoading, mutate } = useSWR(
    ['credentials'],
    () => listCredentials(),
  );
  const [modalPlatform, setModalPlatform] = useState<CredentialPlatform | null>(null);

  const handleDelete = async (id: string) => {
    if (!window.confirm('Révoquer ce compte ?')) return;
    try {
      await deleteCredential(id);
      await mutate();
    } catch (e) {
      window.alert('Erreur : ' + String(e));
    }
  };

  const handleTest = async (id: string) => {
    try {
      const result = await testCredential(id);
      window.alert(
        `Test : ${result.status}` + (result.error !== null ? `\n${result.error}` : ''),
      );
      await mutate();
    } catch (e) {
      window.alert('Erreur : ' + String(e));
    }
  };

  if (error) {
    return <p style={{ color: '#dc2626' }}>Erreur de chargement.</p>;
  }
  if (isLoading) {
    return <p style={{ color: '#6b7280' }}>Chargement…</p>;
  }

  const credentials: UserCredential[] = data ?? [];
  const grouped: Record<CredentialPlatform, UserCredential[]> = {
    youtube: [],
    instagram: [],
    tiktok: [],
  };
  for (const c of credentials) {
    grouped[c.platform].push(c);
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      {PLATFORMS.map(({ value, label }) => (
        <section key={value}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 12,
            }}
          >
            <h2 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 600 }}>{label}</h2>
            <button
              type="button"
              onClick={() => setModalPlatform(value)}
              style={{
                padding: '0.25rem 0.75rem',
                fontSize: '0.875rem',
                borderRadius: 4,
                border: 'none',
                backgroundColor: '#2563eb',
                color: '#fff',
                cursor: 'pointer',
              }}
            >
              + Ajouter un compte {label}
            </button>
          </div>
          <AccountsList
            credentials={grouped[value]}
            onTest={handleTest}
            onDelete={handleDelete}
          />
        </section>
      ))}

      {modalPlatform !== null && (
        <AddAccountModal
          platform={modalPlatform}
          onClose={() => setModalPlatform(null)}
          onSaved={async () => {
            setModalPlatform(null);
            await mutate();
          }}
        />
      )}
    </div>
  );
}
