'use client';

import type { PromptVersion } from '@/lib/types';

interface Props {
  versionA: PromptVersion;
  versionB: PromptVersion;
  onClose: () => void;
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
            overflow: 'auto',
            flex: 1,
          }}
        >
          <div>
            <h3
              style={{
                fontSize: '0.9rem',
                color: '#555',
                marginBottom: '0.5rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
            >
              v{versionA.version_number}
              {versionA.is_system_default && (
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
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                fontSize: '0.8rem',
                background: '#f8f8f8',
                borderRadius: 4,
                padding: '0.75rem',
                margin: 0,
                maxHeight: 600,
                overflow: 'auto',
              }}
            >
              {versionA.template}
            </pre>
          </div>

          <div>
            <h3
              style={{
                fontSize: '0.9rem',
                color: '#555',
                marginBottom: '0.5rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
            >
              v{versionB.version_number}
              {versionB.is_system_default && (
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
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                fontSize: '0.8rem',
                background: '#f8f8f8',
                borderRadius: 4,
                padding: '0.75rem',
                margin: 0,
                maxHeight: 600,
                overflow: 'auto',
              }}
            >
              {versionB.template}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
