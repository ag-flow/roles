import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { WSManager } from '@/lib/ws/connection';

interface StubInstance {
  url: string;
  readyState: number;
  onmessage: ((e: { data: string }) => void) | null;
  onclose: (() => void) | null;
  close: () => void;
}

const instances: StubInstance[] = [];

class WebSocketStub implements StubInstance {
  url: string;
  readyState = 1;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    instances.push(this);
  }

  close(): void {
    if (this.onclose) this.onclose();
  }
}

describe('WSManager', () => {
  const originalWS = globalThis.WebSocket;

  beforeEach(() => {
    instances.length = 0;
    // @ts-expect-error stub
    globalThis.WebSocket = WebSocketStub;
  });

  afterEach(() => {
    globalThis.WebSocket = originalWS;
    vi.useRealTimers();
  });

  it('on(channel, fn) reçoit le payload quand un message arrive', () => {
    const manager = new WSManager();
    manager.connect('ws://test');

    const handler = vi.fn();
    manager.on('source_items_changes', handler);

    const sock = instances[0]!;
    sock.onmessage!({
      data: JSON.stringify({
        channel: 'source_items_changes',
        payload: {
          table: 'source_items',
          op: 'UPDATE',
          tenant_id: 't1',
          id: 'i1',
          status: 'audio_ready',
        },
      }),
    });

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith({
      table: 'source_items',
      op: 'UPDATE',
      tenant_id: 't1',
      id: 'i1',
      status: 'audio_ready',
    });
  });

  it('désinscription via le retour de on() stoppe la livraison', () => {
    const manager = new WSManager();
    manager.connect('ws://test');

    const handler = vi.fn();
    const off = manager.on('runs_changes', handler);
    off();

    const sock = instances[0]!;
    sock.onmessage!({
      data: JSON.stringify({
        channel: 'runs_changes',
        payload: { table: 'runs', op: 'INSERT', tenant_id: 't1', id: 'r1', status: 'queued' },
      }),
    });

    expect(handler).not.toHaveBeenCalled();
  });

  it('onclose déclenche un retry après 3000ms', () => {
    vi.useFakeTimers();
    const manager = new WSManager();
    manager.connect('ws://test');

    expect(instances).toHaveLength(1);

    const sock = instances[0]!;
    sock.onclose!();

    expect(instances).toHaveLength(1);
    vi.advanceTimersByTime(3000);
    expect(instances).toHaveLength(2);
    expect(instances[1]!.url).toBe('ws://test');
  });
});
