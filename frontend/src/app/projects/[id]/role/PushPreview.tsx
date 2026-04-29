'use client';

import type { PushPreview as PushPreviewT } from '@/lib/types';

interface Props {
  preview: PushPreviewT;
}

export function PushPreview({ preview }: Props) {
  return (
    <div style={{ fontSize: '0.875rem' }}>
      <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: '0 0 0.5rem' }}>
        Aperçu du push
      </h3>
      <p style={{ margin: '0.25rem 0', color: '#374151' }}>
        Identity : <strong>{preview.identity_length} caractères</strong>
      </p>
      {preview.target_role_id && (
        <p
          style={{
            margin: '0.25rem 0',
            padding: '0.5rem 0.75rem',
            background: '#eff6ff',
            border: '1px solid #bfdbfe',
            borderRadius: 4,
            color: '#1e40af',
          }}
        >
          Déjà poussé sur ag.flow (id : <code>{preview.target_role_id}</code>)
        </p>
      )}

      <ul style={{ listStyle: 'none', padding: 0, margin: '0.75rem 0' }}>
        {preview.sections.map((s) => (
          <li key={s.name} style={{ marginBottom: '0.5rem' }}>
            <strong>{s.name}</strong>{' '}
            <span style={{ color: '#6b7280' }}>
              ({s.documents.length} document{s.documents.length > 1 ? 's' : ''})
            </span>
            <ul style={{ margin: '0.25rem 0 0 1rem', padding: 0, color: '#374151' }}>
              {s.documents.map((d) => (
                <li key={d.name}>
                  {d.name}{' '}
                  <span style={{ color: '#9ca3af', fontSize: '0.75rem' }}>
                    ({d.size} car.)
                  </span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>

      {!preview.ready_to_push && preview.missing.length > 0 && (
        <div
          style={{
            marginTop: '0.75rem',
            padding: '0.5rem 0.75rem',
            background: '#fef2f2',
            border: '1px solid #fca5a5',
            borderRadius: 4,
            color: '#991b1b',
          }}
        >
          <strong>Éléments manquants :</strong>
          <ul style={{ margin: '0.25rem 0 0 1.25rem', padding: 0 }}>
            {preview.missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
