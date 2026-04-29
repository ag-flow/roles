import type { WSChannel } from '../types';

type Listener = (payload: unknown) => void;

interface QueuedEvent {
  channel: string;
  payload: unknown;
}

export class WSManager {
  private ws: WebSocket | null = null;
  private listeners: Map<WSChannel, Set<Listener>> = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private url: string | null = null;

  connect(url: string): void {
    this.url = url;
    this.openSocket();
  }

  private openSocket(): void {
    if (!this.url) return;
    const socket = new WebSocket(this.url);
    socket.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as QueuedEvent;
        const subs = this.listeners.get(event.channel as WSChannel);
        if (subs) {
          subs.forEach((fn) => fn(event.payload));
        }
      } catch {
        // ignore non-JSON
      }
    };
    socket.onclose = () => {
      this.ws = null;
      this.reconnectTimer = setTimeout(() => this.openSocket(), 3000);
    };
    this.ws = socket;
  }

  on(channel: WSChannel, fn: Listener): () => void {
    if (!this.listeners.has(channel)) {
      this.listeners.set(channel, new Set());
    }
    this.listeners.get(channel)!.add(fn);
    return () => {
      this.listeners.get(channel)?.delete(fn);
    };
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }
}

export const wsManager = new WSManager();
