'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { createSource } from '@/lib/api/sources';
import type { Platform, SourceType } from '@/lib/types';

interface Props {
  roleProjectId: string;
  onClose: () => void;
}

export function AddSourceDialog({ roleProjectId, onClose }: Props) {
  const router = useRouter();
  const [url, setUrl] = useState('');
  const [platform, setPlatform] = useState<Platform>('youtube');
  const [sourceType, setSourceType] = useState<SourceType>('channel');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const source = await createSource(roleProjectId, {
        url,
        platform,
        source_type: sourceType,
      });
      router.push(`/projects/${roleProjectId}/sources/${source.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur inconnue');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-label="Ajouter une source"
      style={{
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        background: '#fff',
        border: '1px solid #d0d7de',
        borderRadius: 8,
        padding: 24,
        boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
        minWidth: 400,
      }}
    >
      <h2 style={{ marginTop: 0 }}>Ajouter une source</h2>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          URL
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            placeholder="https://youtube.com/@chaine"
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          Plateforme
          <select value={platform} onChange={(e) => setPlatform(e.target.value as Platform)}>
            <option value="youtube">YouTube</option>
            <option value="instagram">Instagram</option>
            <option value="tiktok">TikTok</option>
          </select>
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          Type
          <select value={sourceType} onChange={(e) => setSourceType(e.target.value as SourceType)}>
            <option value="single">Vidéo unique</option>
            <option value="channel">Chaîne</option>
            <option value="playlist">Playlist</option>
            <option value="account">Compte</option>
          </select>
        </label>
        {error && <p style={{ color: '#cf222e', margin: 0 }}>{error}</p>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button type="button" onClick={onClose}>
            Annuler
          </button>
          <button type="submit" disabled={loading}>
            {loading ? 'Création…' : 'Créer'}
          </button>
        </div>
      </form>
    </div>
  );
}
