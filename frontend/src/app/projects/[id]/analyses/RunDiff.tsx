'use client';

import type { Run } from '@/lib/types';

interface Props {
  runA: Run;
  runB: Run;
  onClose: () => void;
}

export function RunDiff({ runA, runB, onClose }: Props) {
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
          <h2 style={{ margin: 0, fontSize: '1.1rem' }}>Comparaison de runs</h2>
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
            <h3 style={{ fontSize: '0.9rem', color: '#555', marginBottom: '0.5rem' }}>
              Run A — {runA.id.slice(0, 8)}
              <span
                style={{
                  marginLeft: '0.5rem',
                  fontSize: '0.8rem',
                  color: '#888',
                }}
              >
                {runA.llm_model ?? ''} · {runA.status}
              </span>
            </h3>
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                fontSize: '0.8rem',
                background: '#f8f8f8',
                borderRadius: 4,
                padding: '0.75rem',
                margin: 0,
              }}
            >
              {runA.output ?? '(pas de contenu)'}
            </pre>
          </div>

          <div>
            <h3 style={{ fontSize: '0.9rem', color: '#555', marginBottom: '0.5rem' }}>
              Run B — {runB.id.slice(0, 8)}
              <span
                style={{
                  marginLeft: '0.5rem',
                  fontSize: '0.8rem',
                  color: '#888',
                }}
              >
                {runB.llm_model ?? ''} · {runB.status}
              </span>
            </h3>
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                fontSize: '0.8rem',
                background: '#f8f8f8',
                borderRadius: 4,
                padding: '0.75rem',
                margin: 0,
              }}
            >
              {runB.output ?? '(pas de contenu)'}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
