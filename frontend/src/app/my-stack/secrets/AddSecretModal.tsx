'use client';

import { useRef, useState } from 'react';
import useSWR from 'swr';
import { createSecret, SECRET_TYPE_LABELS } from '@/lib/api/secrets';
import type { SecretType } from '@/lib/api/secrets';
import { listWallets } from '@/lib/api/wallets';
import type { CredentialPlatform } from '@/lib/types';
import { CookiesGuide } from '../social-accounts/CookiesGuide';

interface Props {
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

const TYPE_OPTIONS: SecretType[] = [
  'openai-whisper',
  'deepgram',
  'assemblyai',
  'speechmatics',
  'youtube-cookies',
  'instagram-cookies',
  'tiktok-cookies',
];

const LOCAL_STORAGE_VALUE = 'local';

function isCookiesType(t: SecretType): boolean {
  return t.endsWith('-cookies');
}

function cookiesPlatform(t: SecretType): CredentialPlatform {
  return t.replace('-cookies', '') as CredentialPlatform;
}

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

export function AddSecretModal({ onClose, onSaved }: Props) {
  const { data: wallets } = useSWR(['wallets'], () => listWallets());

  const [secretType, setSecretType] = useState<SecretType>('openai-whisper');
  const [label, setLabel] = useState('');
  const [apiKeyValue, setApiKeyValue] = useState('');
  const [cookiesB64, setCookiesB64] = useState('');
  const [fileName, setFileName] = useState('');
  const [dragging, setDragging] = useState(false);
  // null = pas encore touché par l'utilisateur → présélection calculée ci-dessous
  const [storageChoice, setStorageChoice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const walletList = wallets ?? [];
  const effectiveStorage =
    storageChoice ?? (walletList.length > 0 ? walletList[0]!.id : LOCAL_STORAGE_VALUE);

  const cookiesMode = isCookiesType(secretType);
  const value = cookiesMode ? cookiesB64 : apiKeyValue;

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
    if (!label.trim()) {
      setError('Renseigne un libellé');
      return;
    }
    if (!value) {
      setError(cookiesMode ? 'Sélectionne un fichier cookies.txt' : 'Renseigne la valeur du secret');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createSecret({
        secret_type: secretType,
        label: label.trim(),
        value,
        wallet_id: effectiveStorage === LOCAL_STORAGE_VALUE ? null : effectiveStorage,
      });
      await onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 50,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.5)',
    }}>
      <div style={{ width: '100%', maxWidth: 512, background: 'white', padding: 24, borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.15)', maxHeight: '90vh', overflowY: 'auto' }}>
        <h2 style={{ marginBottom: 16, fontSize: '1.125rem', fontWeight: 600 }}>Ajouter un secret</h2>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Type de secret</span>
          <select
            value={secretType}
            onChange={(e) => setSecretType(e.target.value as SecretType)}
            style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4 }}
          >
            {TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>{SECRET_TYPE_LABELS[t]}</option>
            ))}
          </select>
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Libellé</span>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Ex : Clé OpenAI perso"
            style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4, boxSizing: 'border-box' }}
          />
        </label>

        {cookiesMode ? (
          <div style={{ marginBottom: 12 }}>
            <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
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
            <CookiesGuide platform={cookiesPlatform(secretType)} />
          </div>
        ) : (
          <label style={{ display: 'block', marginBottom: 12 }}>
            <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Clé API</span>
            <input
              type="password"
              value={apiKeyValue}
              onChange={(e) => setApiKeyValue(e.target.value)}
              placeholder="sk-..."
              style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4, boxSizing: 'border-box', fontFamily: 'monospace' }}
            />
          </label>
        )}

        <label style={{ display: 'block', marginBottom: 16 }}>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>Stockage</span>
          <select
            value={effectiveStorage}
            onChange={(e) => setStorageChoice(e.target.value)}
            style={{ width: '100%', padding: '6px 10px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4 }}
          >
            <option value={LOCAL_STORAGE_VALUE}>Local (base chiffrée)</option>
            {walletList.map((w) => (
              <option key={w.id} value={w.id}>{w.label}</option>
            ))}
          </select>
        </label>

        {error !== null && <p style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</p>}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            type="button"
            onClick={onClose}
            style={{ border: '1px solid #d1d5db', padding: '6px 14px', borderRadius: 4, background: 'white', cursor: 'pointer', fontSize: 13 }}
          >
            Annuler
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={submitting || !label.trim() || !value}
            style={{
              background: '#2563eb', color: 'white', padding: '6px 14px', borderRadius: 4, border: 'none',
              cursor: 'pointer', fontSize: 13,
              opacity: submitting || !label.trim() || !value ? 0.5 : 1,
            }}
          >
            {submitting ? 'Ajout…' : 'Ajouter'}
          </button>
        </div>
      </div>
    </div>
  );
}
