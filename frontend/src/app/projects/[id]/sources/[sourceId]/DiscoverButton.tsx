'use client';

import { useState } from 'react';
import { discoverSource } from '@/lib/api/sources';

interface Props {
  sourceId: string;
}

export function DiscoverButton({ sourceId }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setLoading(true);
    setError(null);
    try {
      await discoverSource(sourceId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <button onClick={handleClick} disabled={loading}>
        {loading ? 'Découverte…' : 'Lancer la découverte'}
      </button>
      {error && <span style={{ color: '#cf222e', marginLeft: 8 }}>{error}</span>}
    </div>
  );
}
