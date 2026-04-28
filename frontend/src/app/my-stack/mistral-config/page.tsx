'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { listRoleProjects } from '@/lib/api/role-projects';
import type { RoleProject } from '@/lib/types';
import { StatusIndicator } from '@/components/StatusIndicator';
import { ConfigForm } from './ConfigForm';

export default function MistralConfigPage() {
  const {
    data: projects,
    error,
    isLoading,
    mutate,
  } = useSWR(['role-projects'], () => listRoleProjects());

  const [editing, setEditing] = useState<RoleProject | null>(null);

  if (error !== undefined && error !== null) {
    return <p style={{ color: '#dc2626' }}>Erreur de chargement.</p>;
  }
  if (isLoading) {
    return <p>Chargement…</p>;
  }

  const list = projects ?? [];

  return (
    <div>
      <p style={{ marginBottom: 16, color: '#6b7280', fontSize: 14 }}>
        La clé Mistral n&apos;est pas stockée dans Role Builder mais dans le coffre ag.flow.
        Pour chaque projet, tu peux référencer l&apos;identifiant de ton secret Mistral dans
        ag.flow.
      </p>

      {list.length === 0 ? (
        <p style={{ fontSize: 14 }}>Aucun projet. Crée d&apos;abord un projet.</p>
      ) : (
        <ul
          style={{
            listStyle: 'none',
            padding: 0,
            margin: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          {list.map((p) => (
            <li
              key={p.id}
              style={{ border: '1px solid #e5e7eb', borderRadius: 4, padding: 16 }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600 }}>{p.display_name}</div>
                  <div
                    style={{
                      marginTop: 6,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      fontSize: 13,
                      color: '#6b7280',
                    }}
                  >
                    <StatusIndicator
                      status={
                        p.mistral_secret_ref !== null && p.mistral_secret_ref !== ''
                          ? 'configured'
                          : 'not-configured'
                      }
                      size="sm"
                    />
                    {p.mistral_secret_ref !== null && p.mistral_secret_ref !== '' && (
                      <span>
                        Secret : <code>{p.mistral_secret_ref}</code>
                      </span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setEditing(p)}
                  style={{
                    background: '#2563eb',
                    color: 'white',
                    padding: '6px 12px',
                    borderRadius: 4,
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: 13,
                  }}
                >
                  Configurer
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {editing !== null && (
        <ConfigForm
          project={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await mutate();
          }}
        />
      )}
    </div>
  );
}
