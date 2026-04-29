import { useEffect } from 'react';
import { wsManager } from './connection';
import type { PushEventPayload, WSChannel, WSEventPayload } from '../types';

// Surcharges typées par canal : le caller obtient le bon type de payload
// sans cast.
export function useWebSocketEvent(
  channel: 'agflow_push_events',
  handler: (payload: PushEventPayload) => void,
): void;
export function useWebSocketEvent(
  channel:
    | 'source_items_changes'
    | 'runs_changes'
    | 'workers_changes'
    | 'keys_changes',
  handler: (payload: WSEventPayload) => void,
): void;
export function useWebSocketEvent(
  channel: WSChannel,
  handler: (payload: never) => void,
): void {
  useEffect(() => {
    return wsManager.on(channel, handler as (payload: unknown) => void);
  }, [channel, handler]);
}
