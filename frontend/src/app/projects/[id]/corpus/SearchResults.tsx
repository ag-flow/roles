'use client';

import { ChunkCard } from './ChunkCard';
import type { SearchResult } from '@/lib/types';

interface Props {
  projectId: string;
  results: SearchResult[];
}

export function SearchResults({ projectId, results }: Props) {
  if (results.length === 0) {
    return <p style={{ color: '#666' }}>Aucun résultat.</p>;
  }
  return (
    <div>
      <p style={{ color: '#666', marginBottom: '1rem' }}>{results.length} résultat(s)</p>
      {results.map((r) => (
        <ChunkCard
          key={r.chunk_id}
          projectId={projectId}
          chunk={r}
          similarity={r.similarity}
        />
      ))}
    </div>
  );
}
