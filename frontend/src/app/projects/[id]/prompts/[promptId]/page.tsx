'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import useSWR from 'swr';
import { listPrompts, listVersions, setSystemDefault } from '@/lib/api/prompts';
import type { PromptVersion } from '@/lib/types';
import { VersionEditor } from '../VersionEditor';
import { DiffViewer } from '../DiffViewer';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface VersionRowProps {
  version: PromptVersion;
  onEdit: (v: PromptVersion) => void;
  onSetDefault: (v: PromptVersion) => void;
  onSelectForDiff: (v: PromptVersion) => void;
  diffSelecting: boolean;
  diffA: PromptVersion | null;
}

function VersionRow({
  version,
  onEdit,
  onSetDefault,
  onSelectForDiff,
  diffSelecting,
  diffA,
}: VersionRowProps) {
  const isA = diffA?.id === version.id;

  return (
    <div
      style={{
        border: isA ? '2px solid #1d4ed8' : '1px solid #eaeaea',
        borderRadius: 8,
        padding: '1rem',
        marginBottom: '0.75rem',
        background: isA ? '#eff6ff' : '#fff',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: '1rem',
          marginBottom: '0.5rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <strong style={{ fontSize: '0.95rem' }}>v{version.version_number}</strong>
          {version.is_system_default && (
            <span
              style={{
                display: 'inline-block',
                padding: '2px 8px',
                borderRadius: 4,
                fontSize: '0.75rem',
                fontWeight: 600,
                background: '#dcfce7',
                color: '#15803d',
              }}
            >
              Système
            </span>
          )}
        </div>
        <span style={{ fontSize: '0.8rem', color: '#999' }}>{formatDate(version.created_at)}</span>
      </div>

      <pre
        style={{
          fontSize: '0.8rem',
          background: '#f8f8f8',
          borderRadius: 4,
          padding: '0.5rem 0.75rem',
          margin: '0 0 0.75rem 0',
          whiteSpace: 'pre-wrap',
          overflow: 'hidden',
          maxHeight: '4.5rem',
          color: '#374151',
        }}
      >
        {version.template.length > 200
          ? version.template.slice(0, 200) + '…'
          : version.template}
      </pre>

      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <button onClick={() => onEdit(version)} style={{ fontSize: '0.85rem' }}>
          Voir / éditer
        </button>
        {!version.is_system_default && (
          <button onClick={() => onSetDefault(version)} style={{ fontSize: '0.85rem' }}>
            Restaurer comme système
          </button>
        )}
        {!diffSelecting && (
          <button
            onClick={() => onSelectForDiff(version)}
            style={{ fontSize: '0.85rem' }}
          >
            Comparer
          </button>
        )}
        {diffSelecting && !isA && (
          <button
            onClick={() => onSelectForDiff(version)}
            style={{
              fontSize: '0.85rem',
              background: '#dbeafe',
              color: '#1d4ed8',
              border: '1px solid #93c5fd',
            }}
          >
            Comparer avec v{diffA?.version_number}
          </button>
        )}
      </div>
    </div>
  );
}

export default function PromptDetailPage() {
  const params = useParams();
  const projectId = params['id'] as string;
  const promptId = params['promptId'] as string;

  const { data: prompts } = useSWR('prompts', listPrompts);
  const {
    data: versions,
    error,
    isLoading,
    mutate: mutateVersions,
  } = useSWR(['prompt-versions', promptId], () => listVersions(promptId));

  const prompt = prompts?.find((p) => p.id === promptId);

  // ── modal état ────────────────────────────────────────────────────────────
  const [editingVersion, setEditingVersion] = useState<PromptVersion | null>(null);
  const [newVersion, setNewVersion] = useState(false);

  // diff : sélection en deux clics
  const [diffA, setDiffA] = useState<PromptVersion | null>(null);
  const [diffB, setDiffB] = useState<PromptVersion | null>(null);
  const diffSelecting = diffA !== null && diffB === null;

  function handleSelectForDiff(v: PromptVersion) {
    if (diffA === null) {
      setDiffA(v);
    } else if (diffA.id !== v.id) {
      setDiffB(v);
    }
  }

  function handleCancelDiff() {
    setDiffA(null);
    setDiffB(null);
  }

  async function handleSetDefault(v: PromptVersion) {
    try {
      await setSystemDefault(promptId, v.id);
      await mutateVersions();
    } catch (e) {
      alert(`Erreur : ${String(e)}`);
    }
  }

  return (
    <main style={{ padding: '2rem', maxWidth: 960, margin: '0 auto' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <Link
          href={`/projects/${projectId}/prompts`}
          style={{ fontSize: '0.875rem', color: '#6b7280', textDecoration: 'none' }}
        >
          ← Retour aux prompts
        </Link>
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: '1.5rem',
          gap: '1rem',
        }}
      >
        <div>
          <h1 style={{ marginBottom: '0.25rem' }}>
            {prompt ? prompt.name : promptId}
          </h1>
          {prompt?.description && (
            <p style={{ margin: 0, color: '#666', fontSize: '0.9rem' }}>
              {prompt.description}
            </p>
          )}
        </div>
        <button
          onClick={() => {
            setEditingVersion(null);
            setNewVersion(true);
          }}
          style={{ whiteSpace: 'nowrap' }}
        >
          Nouvelle version
        </button>
      </div>

      {diffSelecting && (
        <div
          style={{
            background: '#dbeafe',
            borderRadius: 6,
            padding: '0.75rem 1rem',
            marginBottom: '1rem',
            fontSize: '0.9rem',
            color: '#1d4ed8',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>
            Sélectionnez une seconde version à comparer avec{' '}
            <strong>v{diffA?.version_number}</strong>.
          </span>
          <button onClick={handleCancelDiff} style={{ fontSize: '0.85rem' }}>
            Annuler
          </button>
        </div>
      )}

      {isLoading && <p style={{ color: '#666' }}>Chargement des versions…</p>}
      {error && (
        <p style={{ color: '#cf222e' }}>
          Erreur lors du chargement : {error instanceof Error ? error.message : 'Erreur inconnue'}
        </p>
      )}

      {versions && versions.length === 0 && !isLoading && (
        <p style={{ color: '#888' }}>Aucune version pour ce prompt.</p>
      )}

      {versions?.map((v) => (
        <VersionRow
          key={v.id}
          version={v}
          onEdit={setEditingVersion}
          onSetDefault={handleSetDefault}
          onSelectForDiff={handleSelectForDiff}
          diffSelecting={diffSelecting}
          diffA={diffA}
        />
      ))}

      {(newVersion || editingVersion !== null) && (
        <VersionEditor
          promptId={promptId}
          initialTemplate={editingVersion?.template ?? ''}
          onSaved={async (newV) => {
            setNewVersion(false);
            setEditingVersion(null);
            await mutateVersions();
            void newV;
          }}
          onCancel={() => {
            setNewVersion(false);
            setEditingVersion(null);
          }}
        />
      )}

      {diffA && diffB && (
        <DiffViewer
          versionA={diffA}
          versionB={diffB}
          onClose={handleCancelDiff}
        />
      )}
    </main>
  );
}
