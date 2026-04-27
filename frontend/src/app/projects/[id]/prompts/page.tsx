'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import useSWR from 'swr';
import { listPrompts } from '@/lib/api/prompts';
import type { Prompt } from '@/lib/types';

const TYPE_LABELS: Record<string, string> = {
  extractor: 'Extracteur',
  clusterer: 'Clusterer',
  decomposer: 'Décomposeur',
  document_writer: 'Rédacteur',
  identity_synthesizer: 'Synthèse identité',
};

function PromptListItem({ prompt, projectId }: { prompt: Prompt; projectId: string }) {
  return (
    <div
      style={{
        border: '1px solid #eaeaea',
        borderRadius: 8,
        padding: '1rem 1.25rem',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '1rem',
      }}
    >
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <strong style={{ fontSize: '1rem' }}>{prompt.name}</strong>
          <span
            style={{
              display: 'inline-block',
              padding: '2px 8px',
              borderRadius: 4,
              fontSize: '0.75rem',
              fontWeight: 600,
              background: '#f0f0f0',
              color: '#555',
            }}
          >
            {TYPE_LABELS[prompt.type] ?? prompt.type}
          </span>
          {prompt.target_section && (
            <span
              style={{
                display: 'inline-block',
                padding: '2px 8px',
                borderRadius: 4,
                fontSize: '0.75rem',
                background: '#dbeafe',
                color: '#1d4ed8',
              }}
            >
              {prompt.target_section}
            </span>
          )}
        </div>
        {prompt.description && (
          <p style={{ margin: 0, fontSize: '0.875rem', color: '#666' }}>
            {prompt.description}
          </p>
        )}
      </div>
      <Link
        href={`/projects/${projectId}/prompts/${prompt.id}`}
        style={{
          padding: '0.4rem 0.9rem',
          border: '1px solid #d1d5db',
          borderRadius: 6,
          fontSize: '0.85rem',
          textDecoration: 'none',
          color: '#374151',
          whiteSpace: 'nowrap',
        }}
      >
        Voir versions
      </Link>
    </div>
  );
}

export default function PromptsPage() {
  const params = useParams();
  const projectId = params['id'] as string;

  const { data: prompts, error, isLoading } = useSWR('prompts', listPrompts);

  return (
    <main style={{ padding: '2rem', maxWidth: 960, margin: '0 auto' }}>
      <h1 style={{ marginBottom: '0.5rem' }}>Prompts système</h1>
      <p style={{ color: '#666', marginBottom: '1.5rem' }}>
        Gérez les templates des 5 étages du pipeline de synthèse. Chaque prompt peut avoir
        plusieurs versions ; la version système est utilisée par défaut.
      </p>

      {isLoading && <p style={{ color: '#666' }}>Chargement des prompts…</p>}
      {error && (
        <p style={{ color: '#cf222e' }}>
          Erreur lors du chargement : {error instanceof Error ? error.message : 'Erreur inconnue'}
        </p>
      )}

      {prompts && prompts.length === 0 && !isLoading && (
        <p style={{ color: '#888' }}>Aucun prompt trouvé.</p>
      )}

      {prompts && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {prompts.map((prompt) => (
            <PromptListItem key={prompt.id} prompt={prompt} projectId={projectId} />
          ))}
        </div>
      )}
    </main>
  );
}
