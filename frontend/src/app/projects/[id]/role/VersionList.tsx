'use client';

import type { RoleDocument } from '@/lib/types';

interface Props {
  versions: RoleDocument[];
  onPromote: (id: string) => void;
  onShowDiff?: (id: string) => void;
}

export function VersionList({ versions, onPromote, onShowDiff }: Props) {
  return (
    <aside
      style={{
        width: 240,
        flexShrink: 0,
        borderLeft: '1px solid #e5e7eb',
        paddingLeft: '0.75rem',
      }}
    >
      <h4
        style={{
          fontSize: '0.75rem',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          color: '#6b7280',
          margin: '0 0 0.5rem',
        }}
      >
        Versions
      </h4>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {versions.map((v) => (
          <li
            key={v.id}
            style={{
              padding: '0.5rem 0',
              borderBottom: '1px solid #f3f4f6',
              fontSize: '0.85rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <strong>v{v.version}</strong>
              {v.is_current && (
                <span
                  style={{
                    fontSize: '0.7rem',
                    background: '#dcfce7',
                    color: '#15803d',
                    padding: '0.05rem 0.4rem',
                    borderRadius: 3,
                    fontWeight: 600,
                  }}
                >
                  current
                </span>
              )}
            </div>
            <div
              style={{
                color: '#9ca3af',
                fontSize: '0.7rem',
                marginTop: '0.15rem',
              }}
            >
              {new Date(v.created_at).toLocaleString('fr-FR')}
            </div>
            {!v.is_current && (
              <div style={{ marginTop: '0.4rem', display: 'flex', gap: '0.4rem' }}>
                <button
                  type="button"
                  onClick={() => onPromote(v.id)}
                  style={{
                    fontSize: '0.75rem',
                    padding: '0.2rem 0.5rem',
                    background: '#2563eb',
                    color: 'white',
                    border: 0,
                    borderRadius: 3,
                    cursor: 'pointer',
                  }}
                >
                  Promouvoir
                </button>
                {onShowDiff && (
                  <button
                    type="button"
                    onClick={() => onShowDiff(v.id)}
                    style={{
                      fontSize: '0.75rem',
                      padding: '0.2rem 0.5rem',
                      background: 'white',
                      color: '#374151',
                      border: '1px solid #d1d5db',
                      borderRadius: 3,
                      cursor: 'pointer',
                    }}
                  >
                    Comparer
                  </button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </aside>
  );
}
