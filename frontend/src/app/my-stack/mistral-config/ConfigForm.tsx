'use client';

import { useState } from 'react';
import { setMistralConfig } from '@/lib/api/mistral-config';
import type { RoleProject } from '@/lib/types';

interface Props {
  project: RoleProject;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

export function ConfigForm({ project, onClose, onSaved }: Props) {
  const [secretRef, setSecretRef] = useState(project.mistral_secret_ref ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await setMistralConfig(project.id, secretRef.trim() || null);
      await onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.5)',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 500,
          background: 'white',
          padding: 24,
          borderRadius: 8,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        }}
      >
        <h2 style={{ marginBottom: 8, fontSize: '1.125rem', fontWeight: 600 }}>
          Configurer Mistral pour {project.display_name}
        </h2>
        <p style={{ marginBottom: 12, fontSize: 13, color: '#6b7280' }}>
          Renseigne l&apos;identifiant de ton secret Mistral tel qu&apos;il est nommé dans ag.flow.
          Le secret réel n&apos;est jamais stocké ici.
        </p>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
            Identifiant du secret Mistral
          </span>
          <input
            type="text"
            value={secretRef}
            onChange={(e) => setSecretRef(e.target.value)}
            placeholder="Ex: mistral-prod-key"
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

        <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 16 }}>
          Laisse vide pour retirer la configuration. Vérifie côté{' '}
          <a
            href="https://docker-agflow.yoops.org"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#2563eb', textDecoration: 'underline' }}
          >
            admin ag.flow
          </a>{' '}
          que le secret existe.
        </p>

        {error !== null && (
          <p style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</p>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              border: '1px solid #d1d5db',
              padding: '6px 14px',
              borderRadius: 4,
              background: 'white',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            Annuler
          </button>
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving}
            style={{
              background: '#2563eb',
              color: 'white',
              padding: '6px 14px',
              borderRadius: 4,
              border: 'none',
              cursor: 'pointer',
              fontSize: 13,
              opacity: saving ? 0.5 : 1,
            }}
          >
            {saving ? 'Enregistrement…' : 'Sauvegarder'}
          </button>
        </div>
      </div>
    </div>
  );
}
