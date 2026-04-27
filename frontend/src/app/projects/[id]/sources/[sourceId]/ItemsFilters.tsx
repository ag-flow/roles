'use client';

import { useState, useEffect } from 'react';
import type { ItemsFilter } from '@/lib/types';

interface Props {
  initial: ItemsFilter;
  onChange: (f: ItemsFilter) => void;
}

export function ItemsFilters({ initial, onChange }: Props) {
  const [minDuration, setMinDuration] = useState<string>(
    initial.min_duration_s?.toString() ?? '',
  );
  const [sinceDate, setSinceDate] = useState<string>(initial.since_date ?? '');
  const [status, setStatus] = useState<string>(initial.status ?? '');

  useEffect(() => {
    onChange({
      min_duration_s: minDuration ? parseInt(minDuration, 10) : undefined,
      since_date: sinceDate || undefined,
      status: status || undefined,
      limit: initial.limit,
      offset: 0,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minDuration, sinceDate, status]);

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'end', marginBottom: 12 }}>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        Durée min (s)
        <input
          type="number"
          min={0}
          value={minDuration}
          onChange={(e) => setMinDuration(e.target.value)}
        />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        Depuis
        <input type="date" value={sinceDate} onChange={(e) => setSinceDate(e.target.value)} />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        Statut
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Tous</option>
          <option value="pending_download">En attente</option>
          <option value="downloading">Téléchargement</option>
          <option value="audio_ready">Audio prêt</option>
          <option value="failed">Échec</option>
        </select>
      </label>
    </div>
  );
}
