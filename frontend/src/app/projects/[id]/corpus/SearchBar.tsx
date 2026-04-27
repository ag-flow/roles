'use client';

import { useState } from 'react';

interface Props {
  onSearch: (query: string) => void | Promise<void>;
  loading: boolean;
}

export function SearchBar({ onSearch, loading }: Props) {
  const [query, setQuery] = useState('');

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void onSearch(query);
      }}
      style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}
    >
      <input
        type="search"
        placeholder="Rechercher dans le corpus..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{ flex: 1, padding: '0.6rem 0.8rem', fontSize: '1rem' }}
        aria-label="Recherche corpus"
      />
      <button type="submit" disabled={loading} style={{ padding: '0.6rem 1.2rem' }}>
        {loading ? 'Recherche...' : 'Rechercher'}
      </button>
    </form>
  );
}
