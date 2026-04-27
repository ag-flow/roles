'use client';

import { useState } from 'react';
import { getAudioUrl } from '@/lib/api/corpus';
import type { Chunk } from '@/lib/types';

interface Props {
  projectId: string;
  chunk: Chunk;
  similarity?: number;
}

function formatTimestamp(s: number | null): string {
  if (s == null) return '—';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}

export function ChunkCard({ projectId, chunk, similarity }: Props) {
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [loadingAudio, setLoadingAudio] = useState(false);

  async function handlePlay() {
    setLoadingAudio(true);
    try {
      const resp = await getAudioUrl(projectId, chunk.source_item_id);
      setAudioUrl(resp.url);
    } catch (err) {
      // Best-effort : si fail, ne casse pas la carte
      console.error(err);
    } finally {
      setLoadingAudio(false);
    }
  }

  return (
    <article
      style={{
        border: '1px solid #eaeaea',
        borderRadius: 8,
        padding: '1rem',
        marginBottom: '1rem',
      }}
    >
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: '0.5rem',
        }}
      >
        <strong>{chunk.source_title ?? 'Sans titre'}</strong>
        <span style={{ color: '#888', fontSize: '0.85rem' }}>
          {formatTimestamp(chunk.start_s)} → {formatTimestamp(chunk.end_s)}
          {similarity !== undefined && ` · ${Math.round(similarity * 100)}%`}
        </span>
      </header>
      <p style={{ marginBottom: '0.5rem' }}>{chunk.text}</p>
      {audioUrl ? (
        <audio controls src={audioUrl} style={{ width: '100%' }} />
      ) : (
        <button
          onClick={handlePlay}
          disabled={loadingAudio}
          style={{ fontSize: '0.85rem' }}
        >
          {loadingAudio ? 'Chargement...' : "Lire l'audio"}
        </button>
      )}
    </article>
  );
}
