'use client';

import { useState } from 'react';
import { createKey } from '@/lib/api/transcription-keys';
import type { TranscriptionProvider } from '@/lib/types';

interface Props {
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

const PROVIDER_OPTIONS: { value: TranscriptionProvider; label: string }[] = [
  { value: 'openai-whisper', label: 'OpenAI Whisper' },
  { value: 'deepgram', label: 'Deepgram' },
  { value: 'assemblyai', label: 'AssemblyAI' },
  { value: 'speechmatics', label: 'Speechmatics' },
];

export function AddKeyModal({ onClose, onSaved }: Props) {
  const [provider, setProvider] = useState<TranscriptionProvider>('openai-whisper');
  const [label, setLabel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [harpocrateKey, setHarpocrateKey] = useState('');
  const [workersCount, setWorkersCount] = useState(1);
  const [isPrimary, setIsPrimary] = useState(false);
  const [isFallback, setIsFallback] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!apiKey.trim()) {
      setError('Renseigne la clé API');
      return;
    }
    if (!harpocrateKey.trim()) {
      setError('Renseigne la clé Harpocrate');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createKey({
        provider,
        label: label || null,
        api_key: apiKey,
        harpocrate_key: harpocrateKey,
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
      <div style={{ width: '100%', maxWidth: 500, background: 'white', padding: 24, borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
        <h2 style={{ marginBottom: 16, fontSize: '1.125rem', fontWeight: 600 }}>Ajouter une clé de transcription</h2>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Provider</span>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value as TranscriptionProvider)}
            style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4 }}
          >
            {PROVIDER_OPTIONS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
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
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Clé API</span>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-..."
            style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4, boxSizing: 'border-box' }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Clé Harpocrate</span>
          <input
            type="text"
            value={harpocrateKey}
            onChange={(e) => setHarpocrateKey(e.target.value)}
            placeholder="ma_cle_openai"
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
          <input
            type="checkbox"
            checked={isPrimary}
            onChange={(e) => setIsPrimary(e.target.checked)}
          />
          <span>Provider primaire</span>
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <input
            type="checkbox"
            checked={isFallback}
            onChange={(e) => setIsFallback(e.target.checked)}
          />
          <span>Activer en fallback</span>
        </label>

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
            onClick={handleSubmit}
            disabled={submitting || !apiKey.trim() || !harpocrateKey.trim()}
            style={{
              background: '#2563eb', color: 'white', padding: '6px 14px', borderRadius: 4, border: 'none',
              cursor: 'pointer', fontSize: 13,
              opacity: submitting || !apiKey.trim() || !harpocrateKey.trim() ? 0.5 : 1,
            }}
          >
            {submitting ? 'Ajout…' : 'Ajouter'}
          </button>
        </div>
      </div>
    </div>
  );
}
