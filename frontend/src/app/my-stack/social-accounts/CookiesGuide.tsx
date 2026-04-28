'use client';

import { useState } from 'react';
import type { CredentialPlatform } from '@/lib/types';

const GUIDES: Record<CredentialPlatform, string[]> = {
  youtube: [
    'Installe l\'extension "Get cookies.txt LOCALLY" sur Chrome ou Firefox.',
    'Va sur youtube.com et connecte-toi à ton compte.',
    'Clique sur l\'icône de l\'extension puis "Export" → enregistre cookies.txt.',
    'Glisse le fichier dans la zone ci-dessus.',
  ],
  instagram: [
    'Installe l\'extension "Get cookies.txt LOCALLY".',
    'Va sur instagram.com et connecte-toi.',
    'Clique sur l\'icône → Export → enregistre cookies.txt.',
    'Glisse le fichier dans la zone ci-dessus.',
  ],
  tiktok: [
    'Installe l\'extension "Get cookies.txt LOCALLY".',
    'Va sur tiktok.com et connecte-toi.',
    'Clique sur l\'icône → Export → enregistre cookies.txt.',
    'Glisse le fichier dans la zone ci-dessus.',
  ],
};

interface Props {
  platform: CredentialPlatform;
}

export function CookiesGuide({ platform }: Props) {
  const [open, setOpen] = useState(false);
  const steps = GUIDES[platform];

  return (
    <div
      style={{
        marginTop: 8,
        borderRadius: 6,
        border: '1px solid #bfdbfe',
        backgroundColor: '#eff6ff',
        padding: '0.75rem',
        fontSize: '0.875rem',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          display: 'flex',
          width: '100%',
          alignItems: 'center',
          justifyContent: 'space-between',
          textAlign: 'left',
          fontWeight: 600,
          color: '#1d4ed8',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: 0,
          fontSize: '0.875rem',
        }}
      >
        <span>Comment exporter mes cookies ?</span>
        <span>{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <ol
          style={{
            marginTop: 8,
            paddingLeft: '1.25rem',
            color: '#1e3a8a',
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
          }}
        >
          {steps.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
      )}
    </div>
  );
}
