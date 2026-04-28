'use client';

import type { UserCredential, CredentialStatus } from '@/lib/types';
import { StatusIndicator } from '@/components/StatusIndicator';
import type { StatusKind } from '@/components/StatusIndicator';

interface Props {
  credentials: UserCredential[];
  onTest: (id: string) => void;
  onDelete: (id: string) => void;
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
}

// CredentialStatus is a subset of StatusKind — safe cast
function toStatusKind(status: CredentialStatus): StatusKind {
  return status as StatusKind;
}

export function AccountsList({ credentials, onTest, onDelete }: Props) {
  if (credentials.length === 0) {
    return (
      <p style={{ fontSize: '0.875rem', color: '#6b7280' }}>Aucun compte configuré.</p>
    );
  }

  return (
    <ul
      style={{
        listStyle: 'none',
        margin: 0,
        padding: 0,
        border: '1px solid #e5e7eb',
        borderRadius: 6,
      }}
    >
      {credentials.map((c, idx) => (
        <li
          key={c.id}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0.75rem 1rem',
            borderTop: idx === 0 ? 'none' : '1px solid #e5e7eb',
          }}
        >
          <div>
            <div style={{ fontWeight: 500, fontSize: '0.9rem' }}>
              {c.label ?? '(sans libellé)'}
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
              <StatusIndicator status={toStatusKind(c.status)} size="sm" />
              <span>Validé : {formatDate(c.last_validated_at)}</span>
              {c.expires_at !== null && (
                <span>Expire : {formatDate(c.expires_at)}</span>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              onClick={() => onTest(c.id)}
              style={{
                padding: '0.25rem 0.75rem',
                fontSize: '0.875rem',
                border: '1px solid #d1d5db',
                borderRadius: 4,
                background: '#fff',
                cursor: 'pointer',
              }}
            >
              Tester
            </button>
            <button
              type="button"
              onClick={() => onDelete(c.id)}
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
              Révoquer
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
