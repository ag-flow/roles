'use client';

import { useState } from 'react';
import { searchCorpus } from '@/lib/api/corpus';
import type { SearchResult } from '@/lib/types';
import { SearchBar } from './SearchBar';
import { SearchResults } from './SearchResults';

interface Props {
  projectId: string;
}

export function CorpusSearchClient({ projectId }: Props) {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  async function handleSearch(q: string) {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    setHasSearched(true);
    try {
      const resp = await searchCorpus(projectId, q);
      setResults(resp.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de recherche');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <SearchBar onSearch={handleSearch} loading={loading} />
      {error && <p style={{ color: '#cf222e' }}>{error}</p>}
      {hasSearched && !loading && (
        <SearchResults projectId={projectId} results={results} />
      )}
    </>
  );
}
