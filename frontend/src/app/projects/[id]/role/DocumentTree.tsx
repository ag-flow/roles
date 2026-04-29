'use client';

import type { RoleDocumentSummary } from '@/lib/types';

interface Props {
  sections: Record<string, RoleDocumentSummary[]>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function DocumentTree({ sections, selectedId, onSelect }: Props) {
  const sectionNames = Object.keys(sections);
  return (
    <nav
      style={{
        width: 260,
        flexShrink: 0,
        borderRight: '1px solid #e5e7eb',
        paddingRight: '0.75rem',
      }}
    >
      {sectionNames.map((name) => (
        <section key={name} style={{ marginBottom: '1rem' }}>
          <h3
            style={{
              fontSize: '0.75rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: '#6b7280',
              margin: '0 0 0.25rem',
            }}
          >
            {name}
          </h3>
          {sections[name]!.length === 0 ? (
            <p style={{ color: '#9ca3af', fontSize: '0.875rem', margin: 0 }}>
              Aucun document
            </p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {sections[name]!.map((doc) => {
                const selected = selectedId === doc.id;
                return (
                  <li key={doc.id}>
                    <button
                      type="button"
                      data-selected={selected}
                      onClick={() => onSelect(doc.id)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.4rem',
                        width: '100%',
                        textAlign: 'left',
                        padding: '0.4rem 0.5rem',
                        background: selected ? '#eff6ff' : 'transparent',
                        border: 0,
                        borderRadius: 4,
                        color: selected ? '#1e40af' : '#374151',
                        fontSize: '0.875rem',
                        cursor: 'pointer',
                      }}
                    >
                      <span style={{ flex: 1 }}>{doc.name}</span>
                      <span
                        style={{
                          fontSize: '0.7rem',
                          color: '#9ca3af',
                          background: '#f3f4f6',
                          padding: '0.05rem 0.35rem',
                          borderRadius: 3,
                        }}
                      >
                        v{doc.version}
                      </span>
                      {doc.locked && (
                        <span
                          aria-label="verrouillé"
                          title="verrouillé"
                          style={{ fontSize: '0.75rem' }}
                        >
                          🔒
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      ))}
    </nav>
  );
}
