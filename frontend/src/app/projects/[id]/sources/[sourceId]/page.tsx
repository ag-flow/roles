'use client';

import { useState, useCallback } from 'react';
import useSWR from 'swr';
import { listItems, selectItems } from '@/lib/api/sources';
import type { SourceItem, ItemsFilter } from '@/lib/types';
import { useWebSocketEvent } from '@/lib/ws/hooks';
import { DiscoverButton } from './DiscoverButton';
import { ItemsTable } from './ItemsTable';
import { ItemsFilters } from './ItemsFilters';
import { SelectionActions } from './SelectionActions';

export default function SourceDetailPage({
  params,
}: {
  params: { id: string; sourceId: string };
}) {
  const [filters, setFilters] = useState<ItemsFilter>({ limit: 50, offset: 0 });
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const { data: items = [], mutate } = useSWR<SourceItem[]>(
    ['items', params.sourceId, filters],
    () => listItems(params.sourceId, filters),
  );

  useWebSocketEvent(
    'source_items_changes',
    useCallback(() => {
      void mutate();
    }, [mutate]),
  );

  const toggle = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(
    (all: boolean) => {
      setSelectedIds(all ? new Set(items.map((i) => i.id)) : new Set());
    },
    [items],
  );

  async function handleIngest() {
    if (selectedIds.size === 0) return;
    await selectItems(params.sourceId, {
      item_ids: Array.from(selectedIds),
      deselect_others: true,
    });
    void mutate();
  }

  return (
    <main style={{ padding: '2rem', maxWidth: 1200 }}>
      <h1>Source</h1>
      <DiscoverButton sourceId={params.sourceId} />
      <div style={{ marginTop: 16 }}>
        <ItemsFilters initial={filters} onChange={setFilters} />
        <SelectionActions
          items={items}
          selectedIds={selectedIds}
          onSetSelection={setSelectedIds}
          onIngest={handleIngest}
        />
        <ItemsTable
          items={items}
          selectedIds={selectedIds}
          onToggle={toggle}
          onToggleAll={toggleAll}
        />
      </div>
    </main>
  );
}
