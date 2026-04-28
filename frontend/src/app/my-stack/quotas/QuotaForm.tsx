'use client';

import { useEffect, useState } from 'react';
import { updateQuota } from '@/lib/api/transcription-keys';
import type { TranscriptionKey } from '@/lib/types';

const PROVIDER_LABELS: Record<TranscriptionKey['provider'], string> = {
  'openai-whisper': 'OpenAI Whisper',
  deepgram: 'Deepgram',
  assemblyai: 'AssemblyAI',
  speechmatics: 'Speechmatics',
};

interface Props {
  keyData: TranscriptionKey;
  onSaved: () => void;
}

export function QuotaForm({ keyData, onSaved }: Props) {
  const [capInput, setCapInput] = useState<string>(
    keyData.monthly_cap_usd != null ? String(keyData.monthly_cap_usd) : '',
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCapInput(keyData.monthly_cap_usd != null ? String(keyData.monthly_cap_usd) : '');
  }, [keyData.monthly_cap_usd]);

  const handleSave = async () => {
    setError(null);
    let cap: number | null = null;
    if (capInput.trim() !== '') {
      const parsed = Number(capInput);
      if (!Number.isFinite(parsed) || parsed < 0) {
        setError('Cap invalide (nombre positif attendu)');
        return;
      }
      cap = parsed;
    }
    setSaving(true);
    try {
      await updateQuota(keyData.id, cap);
      onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const cap = keyData.monthly_cap_usd;
  const spend = keyData.current_month_spend_usd;
  let pct: number | null = null;
  if (cap != null && cap > 0) {
    pct = Math.min(100, (spend / cap) * 100);
  }

  let barColor = '#16a34a';
  if (pct != null) {
    if (pct >= 95) {
      barColor = '#dc2626';
    } else if (pct >= 50) {
      barColor = '#d97706';
    }
  }

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 4, padding: 16 }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 8,
        }}
      >
        <div>
          <div style={{ fontWeight: 600 }}>{PROVIDER_LABELS[keyData.provider]}</div>
          <div style={{ fontSize: 13, color: '#6b7280' }}>{keyData.label ?? '(sans libellé)'}</div>
        </div>
        <div style={{ fontSize: 13 }}>
          <span style={{ fontWeight: 500 }}>${spend.toFixed(2)}</span>
          {cap != null && <span style={{ color: '#6b7280' }}> / ${cap.toFixed(2)}</span>}
        </div>
      </div>

      {pct != null && (
        <div
          style={{
            height: 8,
            background: '#e5e7eb',
            borderRadius: 4,
            marginBottom: 12,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${pct}%`,
              background: barColor,
              transition: 'width 200ms',
            }}
          />
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <label style={{ flex: 1 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>
            Cap mensuel (USD)
          </span>
          <input
            type="number"
            value={capInput}
            min={0}
            step={1}
            onChange={(e) => setCapInput(e.target.value)}
            placeholder="Pas de cap"
            style={{
              width: '100%',
              padding: '6px 10px',
              fontSize: 14,
              border: '1px solid #d1d5db',
              borderRadius: 4,
              boxSizing: 'border-box',
            }}
          />
        </label>
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving}
          style={{
            background: '#2563eb',
            color: 'white',
            padding: '8px 14px',
            borderRadius: 4,
            border: 'none',
            cursor: 'pointer',
            fontSize: 13,
            marginTop: 18,
            opacity: saving ? 0.5 : 1,
          }}
        >
          {saving ? 'Enregistrement…' : 'Sauvegarder'}
        </button>
      </div>

      {error !== null && (
        <p style={{ color: '#dc2626', fontSize: 13, marginTop: 8 }}>{error}</p>
      )}
    </div>
  );
}
