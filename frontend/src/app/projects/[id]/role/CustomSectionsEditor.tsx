'use client';

import { useState } from 'react';
import { updateCustomSections } from '@/lib/api/role-projects';

interface Props {
  projectId: string;
  initial: string[];
  onChange?: (next: string[]) => void;
}

const SECTION_NAME_RE = /^[A-Za-z][A-Za-z0-9_-]{1,31}$/;
const RESERVED = new Set(['Role', 'Missions', 'Skills']);
const MAX_SECTIONS = 5;

function validateNewName(name: string, existing: string[]): string | null {
  if (!name.trim()) return 'Nom vide.';
  if (!SECTION_NAME_RE.test(name)) {
    return 'Format invalide (lettres, chiffres, "-" ou "_", 2-32 caractères).';
  }
  if (RESERVED.has(name)) {
    return `'${name}' est une section standard, pas custom.`;
  }
  if (existing.includes(name)) return `'${name}' déjà ajoutée.`;
  if (existing.length >= MAX_SECTIONS) {
    return `Maximum ${MAX_SECTIONS} sections custom.`;
  }
  return null;
}

export function CustomSectionsEditor({ projectId, initial, onChange }: Props) {
  const [items, setItems] = useState<string[]>(initial);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function persist(next: string[]) {
    setBusy(true);
    setError(null);
    try {
      await updateCustomSections(projectId, next);
      setItems(next);
      onChange?.(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur');
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    const name = draft.trim();
    const validation = validateNewName(name, items);
    if (validation !== null) {
      setError(validation);
      return;
    }
    const next = [...items, name];
    await persist(next);
    setDraft('');
  }

  async function removeAt(index: number) {
    const next = items.filter((_, i) => i !== index);
    await persist(next);
  }

  return (
    <section
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: 6,
        padding: '0.75rem 1rem',
        marginBottom: '1rem',
      }}
    >
      <h3 style={{ margin: '0 0 0.4rem', fontSize: '0.95rem', fontWeight: 600 }}>
        Sections custom
      </h3>
      <p style={{ color: '#6b7280', fontSize: '0.8rem', margin: '0 0 0.6rem' }}>
        En plus des 3 sections standards (Role / Missions / Skills), vous
        pouvez ajouter jusqu&apos;à {MAX_SECTIONS} sections supplémentaires.
        Le decomposer générera un plan de documents pour chacune.
      </p>

      {items.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 0.5rem' }}>
          {items.map((name, i) => (
            <li
              key={name}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.3rem 0.5rem',
                marginBottom: '0.25rem',
                background: '#f3f4f6',
                borderRadius: 4,
                fontSize: '0.85rem',
              }}
            >
              <span style={{ flex: 1, fontFamily: 'monospace' }}>{name}</span>
              <button
                type="button"
                onClick={() => removeAt(i)}
                disabled={busy}
                style={{
                  padding: '0.2rem 0.6rem',
                  background: 'white',
                  color: '#dc2626',
                  border: '1px solid #dc2626',
                  borderRadius: 4,
                  cursor: busy ? 'not-allowed' : 'pointer',
                  fontSize: '0.75rem',
                }}
              >
                Supprimer
              </button>
            </li>
          ))}
        </ul>
      )}

      <div style={{ display: 'flex', gap: '0.4rem' }}>
        <input
          type="text"
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setError(null);
          }}
          placeholder="ex: Outils"
          disabled={busy || items.length >= MAX_SECTIONS}
          style={{
            flex: 1,
            padding: '0.35rem 0.5rem',
            border: '1px solid #d1d5db',
            borderRadius: 4,
            fontSize: '0.85rem',
          }}
        />
        <button
          type="button"
          onClick={add}
          disabled={busy || !draft.trim() || items.length >= MAX_SECTIONS}
          style={{
            padding: '0.35rem 0.8rem',
            background: '#2563eb',
            color: 'white',
            border: 0,
            borderRadius: 4,
            cursor: busy ? 'not-allowed' : 'pointer',
            fontSize: '0.85rem',
            fontWeight: 600,
          }}
        >
          Ajouter
        </button>
      </div>

      {error && (
        <p style={{ marginTop: '0.4rem', color: '#dc2626', fontSize: '0.8rem' }}>
          {error}
        </p>
      )}
    </section>
  );
}
