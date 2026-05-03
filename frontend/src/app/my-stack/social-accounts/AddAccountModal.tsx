'use client';

import { useRef, useState } from 'react';
import { createCredential } from '@/lib/api/credentials';
import type { CredentialPlatform } from '@/lib/types';
import { CookiesGuide } from './CookiesGuide';

interface Props {
  platform: CredentialPlatform;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

const LABELS: Record<CredentialPlatform, string> = {
  youtube: 'YouTube',
  instagram: 'Instagram',
  tiktok: 'TikTok',
};

async function fileToBase64(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) {
    const byte = bytes[i] ?? 0;
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

export function AddAccountModal({ platform, onClose, onSaved }: Props) {
  const [label, setLabel] = useState('');
  const [cookiesB64, setCookiesB64] = useState('');
  const [fileName, setFileName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    setFileName(file.name);
    try {
      const b64 = await fileToBase64(file);
      setCookiesB64(b64);
      setError(null);
    } catch (e) {
      setError('Erreur de lecture du fichier : ' + String(e));
    }
  };

  const handleSubmit = async () => {
    if (!cookiesB64) {
      setError('Sélectionne un fichier cookies.txt');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createCredential({
        platform,
        label: label.trim() !== '' ? label.trim() : null,
        cookies_b64: cookiesB64,
      });
      await onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(0,0,0,0.5)',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 512,
          borderRadius: 8,
          backgroundColor: '#fff',
          padding: '1.5rem',
          boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
        }}
      >
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.125rem', fontWeight: 600 }}>
          Ajouter un compte {LABELS[platform]}
        </h2>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span
            style={{ display: 'block', marginBottom: 4, fontSize: '0.875rem', fontWeight: 500 }}
          >
            Libellé (optionnel)
          </span>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Ex : Compte perso"
            style={{
              width: '100%',
              boxSizing: 'border-box',
              border: '1px solid #d1d5db',
              borderRadius: 4,
              padding: '0.5rem 0.75rem',
              fontSize: '0.875rem',
            }}
          />
        </label>

        <div style={{ marginBottom: 4 }}>
          <span
            style={{ display: 'block', marginBottom: 4, fontSize: '0.875rem', fontWeight: 500 }}
          >
            Fichier cookies.txt
          </span>
          <div
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              const file = e.dataTransfer.files[0];
              if (file) void handleFile(file);
            }}
            style={{
              border: `2px dashed ${dragging ? '#2563eb' : cookiesB64 ? '#16a34a' : '#d1d5db'}`,
              borderRadius: 6,
              padding: '1.25rem',
              textAlign: 'center',
              cursor: 'pointer',
              backgroundColor: dragging ? '#eff6ff' : cookiesB64 ? '#f0fdf4' : '#fafafa',
              transition: 'border-color 0.15s, background-color 0.15s',
              userSelect: 'none',
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,text/plain"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleFile(file);
              }}
              style={{ display: 'none' }}
            />
            {cookiesB64 ? (
              <span style={{ fontSize: '0.875rem', color: '#16a34a', fontWeight: 500 }}>
                ✓ {fileName}
              </span>
            ) : (
              <span style={{ fontSize: '0.875rem', color: '#6b7280' }}>
                {dragging ? 'Relâche pour charger' : 'Glisse le fichier ici ou clique pour parcourir'}
              </span>
            )}
          </div>
        </div>

        <CookiesGuide platform={platform} />

        {error !== null && (
          <p style={{ marginTop: 12, fontSize: '0.875rem', color: '#dc2626' }}>{error}</p>
        )}

        <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '0.5rem 1rem',
              fontSize: '0.875rem',
              border: '1px solid #d1d5db',
              borderRadius: 4,
              background: '#fff',
              cursor: 'pointer',
            }}
          >
            Annuler
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={submitting || cookiesB64 === ''}
            style={{
              padding: '0.5rem 1rem',
              fontSize: '0.875rem',
              borderRadius: 4,
              border: 'none',
              backgroundColor: submitting || cookiesB64 === '' ? '#93c5fd' : '#2563eb',
              color: '#fff',
              cursor: submitting || cookiesB64 === '' ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? 'Ajout…' : 'Ajouter'}
          </button>
        </div>
      </div>
    </div>
  );
}
