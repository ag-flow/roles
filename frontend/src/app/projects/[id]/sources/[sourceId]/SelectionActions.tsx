'use client';

import type { SourceItem } from '@/lib/types';

interface Props {
  items: SourceItem[];
  selectedIds: Set<string>;
  onSetSelection: (ids: Set<string>) => void;
  onIngest: () => void;
}

export function SelectionActions({ items, selectedIds, onSetSelection, onIngest }: Props) {
  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
      <button onClick={() => onSetSelection(new Set(items.map((i) => i.id)))}>
        Tout sélectionner
      </button>
      <button onClick={() => onSetSelection(new Set())}>Tout désélectionner</button>
      <button
        onClick={() => {
          const inverted = new Set<string>();
          items.forEach((i) => {
            if (!selectedIds.has(i.id)) inverted.add(i.id);
          });
          onSetSelection(inverted);
        }}
      >
        Inverser
      </button>
      <button
        onClick={onIngest}
        disabled={selectedIds.size === 0}
        style={{ marginLeft: 'auto' }}
      >
        Lancer l&apos;ingestion ({selectedIds.size})
      </button>
    </div>
  );
}
