'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { listKeys, deleteKey, testKey } from '@/lib/api/transcription-keys';
import { KeysList } from './KeysList';
import { AddKeyModal } from './AddKeyModal';

export default function TranscriptionServicesPage() {
  const { data, error, isLoading, mutate } = useSWR(
    ['transcription-keys'],
    () => listKeys(),
  );
  const [modalOpen, setModalOpen] = useState(false);

  const handleDelete = async (id: string) => {
    if (!window.confirm('Supprimer cette clé ?')) return;
    try {
      await deleteKey(id);
      await mutate();
    } catch (e) {
      window.alert('Erreur : ' + String(e));
    }
  };

  const handleTest = async (id: string) => {
    try {
      const result = await testKey(id);
      const detail = result.error !== null ? `\n${result.error}` : '';
      const balance = result.balance_usd !== null ? `\nBalance : $${result.balance_usd.toFixed(2)}` : '';
      window.alert(`Test : ${result.status}${detail}${balance}`);
      await mutate();
    } catch (e) {
      window.alert('Erreur : ' + String(e));
    }
  };

  if (error) return <p style={{ color: '#dc2626' }}>Erreur de chargement.</p>;
  if (isLoading) return <p>Chargement…</p>;

  const keys = data ?? [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, margin: 0 }}>Clés API SaaS</h2>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          style={{
            background: '#2563eb', color: 'white', padding: '6px 12px',
            borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 14,
          }}
        >
          + Ajouter une clé
        </button>
      </div>

      {keys.length === 0 ? (
        <div style={{
          border: '1px solid #fde68a', background: '#fef3c7',
          padding: 16, borderRadius: 4, fontSize: 14,
        }}>
          <strong>Aucune clé active.</strong> Les transcriptions utiliseront le pool partagé
          (faster-whisper local) avec une queue commune à tous les utilisateurs.
        </div>
      ) : (
        <KeysList
          keys={keys}
          onTest={handleTest}
          onDelete={handleDelete}
          onChanged={async () => { await mutate(); }}
        />
      )}

      {modalOpen && (
        <AddKeyModal
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
