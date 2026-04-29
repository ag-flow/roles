'use client';

import { useState } from 'react';
import { updateRoleDocumentContent } from '@/lib/api/role-documents';
import type { RoleDocument } from '@/lib/types';

interface Props {
  doc: RoleDocument;
  onSaved: () => void;
}

export function DocumentEditor({ doc, onSaved }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(doc.content);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const dirty = draft !== doc.content;

  function startEdit() {
    setDraft(doc.content);
    setSaveError(null);
    setEditing(true);
  }

  function cancel() {
    setEditing(false);
    setSaveError(null);
  }

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      await updateRoleDocumentContent(doc.id, draft);
      setEditing(false);
      onSaved();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Erreur inconnue');
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <section>
        <pre
          style={{
            padding: '1rem',
            background: '#f9fafb',
            border: '1px solid #e5e7eb',
            borderRadius: 6,
            fontSize: '0.875rem',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            margin: 0,
          }}
        >
          {doc.content}
        </pre>
        <div style={{ marginTop: '0.5rem' }}>
          <button
            type="button"
            onClick={startEdit}
            disabled={doc.locked}
            title={doc.locked ? 'Document verrouillé — déverrouille-le pour éditer' : ''}
            style={{
              padding: '0.4rem 0.9rem',
              background: '#2563eb',
              color: 'white',
              border: 0,
              borderRadius: 4,
              cursor: doc.locked ? 'not-allowed' : 'pointer',
              opacity: doc.locked ? 0.5 : 1,
              fontSize: '0.875rem',
            }}
          >
            Éditer
          </button>
        </div>
      </section>
    );
  }

  return (
    <section>
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={20}
        style={{
          width: '100%',
          padding: '0.75rem',
          fontFamily:
            'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
          fontSize: '0.875rem',
          border: '1px solid #d1d5db',
          borderRadius: 6,
          resize: 'vertical',
        }}
      />
      {saveError && (
        <pre
          style={{
            margin: '0.5rem 0 0',
            padding: '0.5rem',
            background: '#fef2f2',
            color: '#991b1b',
            fontSize: '0.75rem',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {saveError}
        </pre>
      )}
      <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
        <button
          type="button"
          onClick={cancel}
          style={{
            padding: '0.4rem 0.9rem',
            background: 'white',
            border: '1px solid #d1d5db',
            borderRadius: 4,
            cursor: 'pointer',
            fontSize: '0.875rem',
          }}
        >
          Annuler
        </button>
        <button
          type="button"
          onClick={save}
          disabled={saving || !dirty}
          style={{
            padding: '0.4rem 0.9rem',
            background: '#16a34a',
            color: 'white',
            border: 0,
            borderRadius: 4,
            cursor: saving || !dirty ? 'not-allowed' : 'pointer',
            opacity: saving || !dirty ? 0.5 : 1,
            fontSize: '0.875rem',
            fontWeight: 600,
          }}
        >
          {saving ? 'Enregistrement…' : 'Enregistrer'}
        </button>
      </div>
    </section>
  );
}
