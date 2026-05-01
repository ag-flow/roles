'use client';

import { ColoredDiff } from '@/components/ColoredDiff';
import type { PromptVersion } from '@/lib/types';

interface Props {
  versionA: PromptVersion;
  versionB: PromptVersion;
  onClose: () => void;
}

function VersionHeader({ version }: { version: PromptVersion }) {
  return (
    <h3
      style={{
        fontSize: '0.9rem',
        color: '#555',
        margin: 0,
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
      }}
    >
      v{version.version_number}
      {version.is_system_default && (
        <span
          style={{
            padding: '2px 6px',
            borderRadius: 4,
            fontSize: '0.75rem',
            fontWeight: 600,
            background: '#dcfce7',
            color: '#15803d',
          }}
        >
          système
        </span>
      )}
    </h3>
  );
}

export function DiffViewer({ versionA, versionB, onClose }: Props) {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 200,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#fff',
          borderRadius: 8,
          padding: '1.5rem',
          width: '90vw',
          maxWidth: 1200,
          maxHeight: '85vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '1rem',
          }}
        >
          <h2 style={{ margin: 0, fontSize: '1.1rem' }}>Comparaison versions</h2>
          <button onClick={onClose}>Fermer</button>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '1rem',
            marginBottom: '0.5rem',
          }}
        >
          <VersionHeader version={versionA} />
          <VersionHeader version={versionB} />
        </div>

        <div style={{ overflow: 'auto', flex: 1, fontSize: '0.85rem' }}>
          <ColoredDiff
            oldValue={versionA.template}
            newValue={versionB.template}
          />
        </div>
      </div>
    </div>
  );
}
