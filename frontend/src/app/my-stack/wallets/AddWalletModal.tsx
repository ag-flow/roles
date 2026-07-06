'use client';

import { useState } from 'react';
import { createWallet } from '@/lib/api/wallets';

interface Props {
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

const DEFAULT_API_URL = 'https://vault.yoops.org';

export function AddWalletModal({ onClose, onSaved }: Props) {
  const [label, setLabel] = useState('');
  const [apiToken, setApiToken] = useState('');
  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!label.trim()) {
      setError('Renseigne un libellé');
      return;
    }
    if (!apiToken.trim()) {
      setError('Renseigne le token API');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createWallet({
        label: label.trim(),
        api_token: apiToken.trim(),
        api_url: apiUrl.trim() !== '' ? apiUrl.trim() : undefined,
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
        <h2 style={{ marginBottom: 16, fontSize: '1.125rem', fontWeight: 600 }}>Ajouter un wallet Harpocrate</h2>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Libellé</span>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Ex : Mon coffre perso"
            style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4, boxSizing: 'border-box' }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Token API</span>
          <input
            type="password"
            value={apiToken}
            onChange={(e) => setApiToken(e.target.value)}
            placeholder="hrpv_..."
            style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4, boxSizing: 'border-box', fontFamily: 'monospace' }}
          />
        </label>

        <div style={{ marginBottom: 16 }}>
          <button
            type="button"
            onClick={() => setAdvancedOpen((o) => !o)}
            style={{
              background: 'none', border: 'none', padding: 0, cursor: 'pointer',
              fontSize: 13, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 4,
            }}
          >
            <span>{advancedOpen ? '▲' : '▼'}</span>
            <span>Avancé</span>
          </button>
          {advancedOpen && (
            <label style={{ display: 'block', marginTop: 8 }}>
              <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>URL de l&apos;API</span>
              <input
                type="text"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                placeholder={DEFAULT_API_URL}
                style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4, boxSizing: 'border-box', fontFamily: 'monospace' }}
              />
            </label>
          )}
        </div>

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
            disabled={submitting || !label.trim() || !apiToken.trim()}
            style={{
              background: '#2563eb', color: 'white', padding: '6px 14px', borderRadius: 4, border: 'none',
              cursor: 'pointer', fontSize: 13,
              opacity: submitting || !label.trim() || !apiToken.trim() ? 0.5 : 1,
            }}
          >
            {submitting ? 'Ajout…' : 'Ajouter'}
          </button>
        </div>
      </div>
    </div>
  );
}
