'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { listWallets, deleteWallet } from '@/lib/api/wallets';
import { ApiError } from '@/lib/api/client';
import { StatusIndicator } from '@/components/StatusIndicator';
import type { StatusKind } from '@/components/StatusIndicator';
import { AddWalletModal } from './AddWalletModal';

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

export default function WalletsPage() {
  const { data, error, isLoading, mutate } = useSWR(['wallets'], () => listWallets());
  const [modalOpen, setModalOpen] = useState(false);

  const handleDelete = async (id: string) => {
    if (!window.confirm('Supprimer ce wallet ?')) return;
    try {
      await deleteWallet(id);
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

  const wallets = data ?? [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, margin: 0 }}>Coffres Harpocrate</h2>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          style={{
            background: '#2563eb', color: 'white', padding: '6px 12px',
            borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 14,
          }}
        >
          + Ajouter un wallet
        </button>
      </div>

      {wallets.length === 0 ? (
        <div style={{
          border: '1px solid #bfdbfe', background: '#eff6ff',
          padding: 16, borderRadius: 4, fontSize: 14, color: '#1e3a8a',
        }}>
          <strong>Aucun wallet — et ce n&apos;est pas obligatoire.</strong> Vos secrets peuvent
          être stockés localement, chiffrés dans la base. Ajouter un wallet Harpocrate permet
          de les conserver dans votre propre coffre plutôt que dans cette application.
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
          {wallets.map((w, idx) => (
            <li
              key={w.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                borderTop: idx === 0 ? 'none' : '1px solid #e5e7eb',
              }}
            >
              <div>
                <div style={{ fontWeight: 500, fontSize: '0.9rem' }}>{w.label}</div>
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
                  <StatusIndicator status={w.status as StatusKind} size="sm" />
                  <span style={{ fontFamily: 'monospace' }}>{w.api_url}</span>
                  <span>Ajouté : {formatDate(w.created_at)}</span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => void handleDelete(w.id)}
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
        <AddWalletModal
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
