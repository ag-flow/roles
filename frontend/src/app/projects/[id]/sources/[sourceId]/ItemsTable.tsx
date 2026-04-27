'use client';

import type { SourceItem } from '@/lib/types';

interface Props {
  items: SourceItem[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
  onToggleAll: (allSelected: boolean) => void;
}

function formatDuration(s: number | null): string {
  if (s == null) return '—';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    : `${m}:${String(sec).padStart(2, '0')}`;
}

export function ItemsTable({ items, selectedIds, onToggle, onToggleAll }: Props) {
  const allSelected = items.length > 0 && items.every((i) => selectedIds.has(i.id));

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ borderBottom: '2px solid #d0d7de' }}>
          <th style={{ padding: 8 }}>
            <input
              type="checkbox"
              checked={allSelected}
              onChange={(e) => onToggleAll(e.target.checked)}
              aria-label="Tout sélectionner"
            />
          </th>
          <th style={{ textAlign: 'left', padding: 8 }}>Vidéo</th>
          <th style={{ padding: 8 }}>Durée</th>
          <th style={{ padding: 8 }}>Publication</th>
          <th style={{ padding: 8 }}>Statut</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.id} style={{ borderTop: '1px solid #eaeaea' }}>
            <td style={{ padding: 8, textAlign: 'center' }}>
              <input
                type="checkbox"
                checked={selectedIds.has(item.id)}
                onChange={() => onToggle(item.id)}
                aria-label={`Sélectionner ${item.title ?? item.platform_item_id}`}
              />
            </td>
            <td style={{ padding: 8 }}>{item.title ?? item.platform_item_id}</td>
            <td style={{ padding: 8, textAlign: 'center' }}>{formatDuration(item.duration_s)}</td>
            <td style={{ padding: 8, textAlign: 'center' }}>
              {item.published_at ? new Date(item.published_at).toLocaleDateString('fr-FR') : '—'}
            </td>
            <td style={{ padding: 8, textAlign: 'center' }}>{item.status}</td>
          </tr>
        ))}
        {items.length === 0 && (
          <tr>
            <td colSpan={5} style={{ textAlign: 'center', padding: 16, color: '#666' }}>
              Aucun item.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
