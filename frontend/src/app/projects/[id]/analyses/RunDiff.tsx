'use client';

import { ColoredDiff } from '@/components/ColoredDiff';
import type { Run } from '@/lib/types';

interface Props {
  runA: Run;
  runB: Run;
  onClose: () => void;
}

function runHeader(run: Run, label: string): string {
  const model = run.llm_model ?? '';
  return `${label} — ${run.id.slice(0, 8)} · ${model} · ${run.status}`;
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

        <div style={{ overflow: 'auto', flex: 1, fontSize: '0.85rem' }}>
          <ColoredDiff
            oldValue={runA.output ?? ''}
            newValue={runB.output ?? ''}
            leftTitle={runHeader(runA, 'Run A')}
            rightTitle={runHeader(runB, 'Run B')}
          />
        </div>
      </div>
    </div>
  );
}
