import { useEffect } from 'react';
import { wsManager } from './connection';
import type { WSChannel, WSEventPayload } from '../types';

export function useWebSocketEvent(
  channel: WSChannel,
  handler: (payload: WSEventPayload) => void,
): void {
  useEffect(() => {
    return wsManager.on(channel, handler);
  }, [channel, handler]);
}
