'use client';

import type { TranscriptionKey, TranscriptionKeyStatus } from '@/lib/types';
import { StatusIndicator } from '@/components/StatusIndicator';
import { KeySettings } from './KeySettings';
import { BalanceBadge } from './BalanceBadge';

const PROVIDER_LABELS: Record<TranscriptionKey['provider'], string> = {
  'openai-whisper': 'OpenAI Whisper',
  deepgram: 'Deepgram',
  assemblyai: 'AssemblyAI',
  speechmatics: 'Speechmatics',
};

interface Props {
  keys: TranscriptionKey[];
  onTest: (id: string) => void;
  onDelete: (id: string) => void;
  onChanged: () => void | Promise<void>;
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
}

export function KeysList({ keys, onTest, onDelete, onChanged }: Props) {
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {keys.map((k) => (
        <li key={k.id} style={{ border: '1px solid #e5e7eb', borderRadius: 4, padding: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontWeight: 600 }}>{PROVIDER_LABELS[k.provider]}</div>
              <div style={{ marginTop: 4, fontSize: 13, color: '#6b7280' }}>
                {k.label ?? '(sans libellé)'}
              </div>
              <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 12, fontSize: 12, color: '#6b7280' }}>
                <StatusIndicator status={k.status as TranscriptionKeyStatus} size="sm" />
                <span>Validée : {formatDate(k.last_validated_at)}</span>
                <BalanceBadge balance={k.current_balance_usd} cap={k.monthly_cap_usd} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                onClick={() => onTest(k.id)}
                style={{ border: '1px solid #d1d5db', padding: '4px 10px', borderRadius: 4, background: 'white', cursor: 'pointer', fontSize: 13 }}
              >
                Tester
              </button>
              <button
                type="button"
                onClick={() => onDelete(k.id)}
                style={{ border: '1px solid #fca5a5', color: '#dc2626', padding: '4px 10px', borderRadius: 4, background: 'white', cursor: 'pointer', fontSize: 13 }}
              >
                Supprimer
              </button>
            </div>
          </div>

          <KeySettings keyData={k} onChanged={onChanged} />
        </li>
      ))}
    </ul>
  );
}
