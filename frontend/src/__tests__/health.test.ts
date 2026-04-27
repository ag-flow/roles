import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchHealth } from '@/lib/api/health';

describe('fetchHealth', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('renvoie le payload quand le backend répond ok', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: 'ok', db: true }),
    } as Response));

    const result = await fetchHealth('http://api.test');
    expect(result).toEqual({ status: 'ok', db: true });
  });

  it('renvoie unreachable si le fetch échoue', async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error('connection refused');
    });

    const result = await fetchHealth('http://api.test');
    expect(result).toEqual({ status: 'unreachable', db: false });
  });

  it('renvoie unreachable si le backend renvoie 5xx', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'unavailable' }),
    } as Response));

    const result = await fetchHealth('http://api.test');
    expect(result).toEqual({ status: 'unreachable', db: false });
  });
});
