'use client';

import { useState } from 'react';
import type { Run } from '@/lib/types';

interface Props {
  run: Run;
  onCompare?: (run: Run) => void;
}

const STATUS_STYLES: Record<string, { background: string; color: string; label: string }> = {
  pending: { background: '#f0f0f0', color: '#666', label: 'En attente' },
  running: { background: '#dbeafe', color: '#1d4ed8', label: 'En cours' },
  done: { background: '#dcfce7', color: '#15803d', label: 'Terminé' },
  failed: { background: '#fee2e2', color: '#b91c1c', label: 'Échoué' },
};

function formatRelativeDate(iso: string | null): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'à l\'instant';
  if (mins < 60) return `il y a ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `il y a ${hrs} h`;
  return new Date(iso).toLocaleDateString('fr-FR');
}

function formatCost(usd: number | null): string {
  if (usd == null) return '—';
  return `$${usd.toFixed(4)}`;
}

function formatTokens(n: number | null): string {
  if (n == null) return '—';
  return n.toLocaleString('fr-FR');
}

export function RunCard({ run, onCompare }: Props) {
  const [showOutput, setShowOutput] = useState(false);
  const style = STATUS_STYLES[run.status] ?? STATUS_STYLES['pending']!;

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
          alignItems: 'flex-start',
          marginBottom: '0.75rem',
          gap: '1rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span
            style={{
              display: 'inline-block',
              padding: '2px 8px',
              borderRadius: 4,
              fontSize: '0.8rem',
              fontWeight: 600,
              background: style.background,
              color: style.color,
            }}
          >
            {style.label}
          </span>
          <span style={{ fontSize: '0.85rem', color: '#666' }}>
            {run.llm_model ?? '—'}
          </span>
        </div>
        <span style={{ fontSize: '0.8rem', color: '#999' }}>
          {formatRelativeDate(run.created_at)}
        </span>
      </header>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '0.5rem',
          fontSize: '0.85rem',
          color: '#555',
          marginBottom: '0.75rem',
        }}
      >
        <div>
          <span style={{ color: '#999' }}>Tokens in : </span>
          {formatTokens(run.tokens_input)}
        </div>
        <div>
          <span style={{ color: '#999' }}>Tokens out : </span>
          {formatTokens(run.tokens_output)}
        </div>
        <div>
          <span style={{ color: '#999' }}>Coût : </span>
          {formatCost(run.cost_usd)}
        </div>
      </div>

      {run.status === 'failed' && run.error && (
        <p
          style={{
            fontSize: '0.85rem',
            color: '#b91c1c',
            background: '#fee2e2',
            borderRadius: 4,
            padding: '0.5rem',
            marginBottom: '0.75rem',
          }}
        >
          {run.error}
        </p>
      )}

      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <button
          onClick={() => setShowOutput(true)}
          disabled={!run.output}
          style={{ fontSize: '0.85rem' }}
        >
          Voir output
        </button>
        <button
          onClick={() => onCompare?.(run)}
          disabled={!onCompare}
          title={onCompare ? 'Comparer avec un autre run' : 'Fonctionnalité disponible depuis la liste'}
          style={{ fontSize: '0.85rem' }}
        >
          Comparer
        </button>
      </div>

      {showOutput && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
          }}
          onClick={() => setShowOutput(false)}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: 8,
              padding: '1.5rem',
              maxWidth: '80vw',
              maxHeight: '80vh',
              overflow: 'auto',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginBottom: '1rem',
              }}
            >
              <strong>Output — run {run.id.slice(0, 8)}</strong>
              <button onClick={() => setShowOutput(false)}>Fermer</button>
            </div>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: '0.85rem' }}>
              {run.output ?? '(pas de contenu)'}
            </pre>
          </div>
        </div>
      )}
    </article>
  );
}
