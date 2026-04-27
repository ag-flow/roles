'use client';

import { useState } from 'react';
import { createVersion } from '@/lib/api/prompts';
import type { PromptVersion } from '@/lib/types';

interface Props {
  promptId: string;
  initialTemplate: string;
  onSaved: (newVersion: PromptVersion) => void;
  onCancel: () => void;
}

export function VersionEditor({ promptId, initialTemplate, onSaved, onCancel }: Props) {
  const [template, setTemplate] = useState(initialTemplate);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const v = await createVersion(promptId, template);
      onSaved(v);
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
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
      onClick={onCancel}
    >
      <div
        style={{
          background: '#fff',
          borderRadius: 8,
          padding: '1.5rem',
          width: '90vw',
          maxWidth: 800,
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ margin: '0 0 0.5rem 0', fontSize: '1.1rem' }}>
          Édition du template
        </h2>
        <p
          style={{
            margin: '0 0 0.75rem 0',
            fontSize: '0.8rem',
            color: '#6b7280',
            fontFamily: 'monospace',
          }}
        >
          Placeholders disponibles :{' '}
          {'{global_directives}'}, {'{chunks}'}, {'{signals}'}, {'{clusters}'}, {'{documents}'}
        </p>
        <textarea
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
          rows={25}
          style={{
            fontFamily: 'monospace',
            fontSize: '0.85rem',
            width: '100%',
            flex: 1,
            resize: 'vertical',
            border: '1px solid #d1d5db',
            borderRadius: 4,
            padding: '0.5rem',
            lineHeight: 1.5,
          }}
        />
        {error && (
          <p
            style={{
              margin: '0.5rem 0 0 0',
              fontSize: '0.875rem',
              color: '#b91c1c',
              background: '#fee2e2',
              borderRadius: 4,
              padding: '0.4rem 0.6rem',
            }}
          >
            {error}
          </p>
        )}
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
          <button
            onClick={handleSave}
            disabled={saving || !template.trim()}
            style={{
              padding: '0.4rem 0.9rem',
              fontSize: '0.875rem',
              cursor: saving || !template.trim() ? 'not-allowed' : 'pointer',
              opacity: saving || !template.trim() ? 0.6 : 1,
            }}
          >
            {saving ? 'Sauvegarde…' : 'Créer une nouvelle version'}
          </button>
          <button
            onClick={onCancel}
            style={{ padding: '0.4rem 0.9rem', fontSize: '0.875rem' }}
          >
            Annuler
          </button>
        </div>
      </div>
    </div>
  );
}
