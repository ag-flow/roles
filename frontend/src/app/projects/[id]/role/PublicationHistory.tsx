'use client';

import useSWR from 'swr';
import { listPublications } from '@/lib/api/github';

interface Props {
  projectId: string;
  repoFullName: string | null;
}

export function PublicationHistory({ projectId, repoFullName }: Props) {
  const { data, isLoading } = useSWR(['publications', projectId], () =>
    listPublications(projectId),
  );
  if (isLoading) return <p style={{ color: '#6b7280' }}>Chargement…</p>;
  if (!data || data.length === 0) {
    return (
      <p style={{ color: '#6b7280', fontStyle: 'italic', margin: 0 }}>
        Aucune publication pour ce rôle.
      </p>
    );
  }

  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
      {data.map((p) => {
        const sha7 = p.commit_sha.slice(0, 7);
        const commitUrl = repoFullName
          ? `https://github.com/${repoFullName}/commit/${p.commit_sha}`
          : null;
        return (
          <li
            key={p.id}
            style={{
              padding: '0.5rem 0',
              borderBottom: '1px solid #f3f4f6',
              fontSize: '0.85rem',
            }}
          >
            {commitUrl ? (
              <a
                href={commitUrl}
                target="_blank"
                rel="noopener noreferrer"
                style={{ fontFamily: 'monospace' }}
              >
                {sha7}
              </a>
            ) : (
              <code>{sha7}</code>
            )}{' '}
            — {new Date(p.published_at).toLocaleString('fr-FR')}
            {' · '}
            {p.files_count ?? 0} fichier(s)
            {p.summary && (
              <div style={{ color: '#6b7280', fontSize: '0.75rem' }}>
                {p.summary}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
