'use client';

import { useEffect, useRef, useState } from 'react';
import { updateKey } from '@/lib/api/transcription-keys';
import type { TranscriptionKey } from '@/lib/types';

interface Props {
  keyData: TranscriptionKey;
  onChanged: () => void | Promise<void>;
}

export function KeySettings({ keyData, onChanged }: Props) {
  const [workersCount, setWorkersCount] = useState(keyData.workers_count);
  const [isPrimary, setIsPrimary] = useState(keyData.is_primary);
  const [isFallback, setIsFallback] = useState(keyData.is_fallback);
  const [saving, setSaving] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync state si la prop change (mutate de SWR)
  useEffect(() => {
    setWorkersCount(keyData.workers_count);
    setIsPrimary(keyData.is_primary);
    setIsFallback(keyData.is_fallback);
  }, [keyData.workers_count, keyData.is_primary, keyData.is_fallback]);

  const persist = async (next: { workers_count?: number; is_primary?: boolean; is_fallback?: boolean }) => {
    setSaving(true);
    try {
      await updateKey(keyData.id, next);
      await onChanged();
    } catch (e) {
      window.alert('Erreur de sauvegarde : ' + String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleSliderChange = (v: number) => {
    setWorkersCount(v);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      void persist({ workers_count: v });
    }, 500);
  };

  return (
    <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>Workers : {workersCount}</span>
          <input
            type="range"
            min={1}
            max={5}
            step={1}
            value={workersCount}
            onChange={(e) => handleSliderChange(Number(e.target.value))}
            style={{ width: 200 }}
          />
        </label>
        {saving && <span style={{ color: '#6b7280', fontSize: 12 }}>(enregistrement…)</span>}
      </div>

      <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input
          type="checkbox"
          checked={isPrimary}
          onChange={async (e) => {
            const checked = e.target.checked;
            setIsPrimary(checked);
            await persist({ is_primary: checked });
          }}
        />
        <span>Provider primaire</span>
      </label>

      <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input
          type="checkbox"
          checked={isFallback}
          onChange={async (e) => {
            const checked = e.target.checked;
            setIsFallback(checked);
            await persist({ is_fallback: checked });
          }}
        />
        <span>Activer en fallback</span>
      </label>
    </div>
  );
}
