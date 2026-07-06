import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  listCredentials,
  createCredential,
  testCredential,
  deleteCredential,
} from '@/lib/api/credentials';
import {
  listKeys,
  createKey,
  updateKey,
  testKey,
  updateQuota,
  getUsage,
  deleteKey,
} from '@/lib/api/transcription-keys';

interface FetchCall {
  url: string;
  init: RequestInit;
}

function mockFetch(
  response: Partial<Response> & {
    json?: () => Promise<unknown>;
    text?: () => Promise<string>;
  },
): {
  calls: FetchCall[];
  fn: typeof globalThis.fetch;
} {
  const calls: FetchCall[] = [];
  const fn = vi.fn(async (url: string | URL | Request, init: RequestInit = {}) => {
    calls.push({ url: String(url), init });
    return {
      ok: true,
      status: 200,
      json: async () => ({}),
      text: async () => '',
      ...response,
    } as Response;
  }) as unknown as typeof globalThis.fetch;
  return { calls, fn };
}

// ─── Credentials ──────────────────────────────────────────────────────────────

describe('credentials API client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('listCredentials envoie GET sur /api/credentials sans querystring', async () => {
    const payload = [{ id: 'cred-1', platform: 'youtube' }];
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await listCredentials();

    expect(result).toEqual(payload);
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe('/api/credentials');
    expect(calls[0]!.init.method).toBeUndefined();
  });

  it('listCredentials avec platform ajoute ?platform=youtube', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;

    await listCredentials('youtube');

    expect(calls[0]!.url).toBe('/api/credentials?platform=youtube');
  });

  it('createCredential envoie POST avec body JSON', async () => {
    const payload = { id: 'cred-2', platform: 'instagram', label: 'mon compte', status: 'active' };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await createCredential({
      secret_id: 'secret-1',
      label: 'mon compte',
    });

    expect(result).toEqual(payload);
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe('/api/credentials');
    expect(calls[0]!.init.method).toBe('POST');
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
      secret_id: 'secret-1',
      label: 'mon compte',
    });
  });

  it('testCredential envoie POST sur /api/credentials/{id}/test', async () => {
    const payload = { status: 'active', last_validated_at: '2026-01-01T00:00:00Z', error: null };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await testCredential('cred-1');

    expect(result).toEqual(payload);
    expect(calls[0]!.url).toBe('/api/credentials/cred-1/test');
    expect(calls[0]!.init.method).toBe('POST');
  });

  it('deleteCredential envoie DELETE sur /api/credentials/{id}', async () => {
    const { calls, fn } = mockFetch({ status: 204, json: async () => undefined });
    globalThis.fetch = fn;

    await deleteCredential('cred-1');

    expect(calls[0]!.url).toBe('/api/credentials/cred-1');
    expect(calls[0]!.init.method).toBe('DELETE');
  });
});

// ─── Transcription Keys ───────────────────────────────────────────────────────

describe('transcription-keys API client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('listKeys envoie GET sur /api/transcription-keys', async () => {
    const payload = [{ id: 'key-1', provider: 'deepgram' }];
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await listKeys();

    expect(result).toEqual(payload);
    expect(calls[0]!.url).toBe('/api/transcription-keys');
    expect(calls[0]!.init.method).toBeUndefined();
  });

  it('createKey envoie POST avec body JSON', async () => {
    const payload = { id: 'key-2', provider: 'deepgram', status: 'active' };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await createKey({
      secret_id: 'secret-1',
      label: 'ma clé deepgram',
      workers_count: 2,
    });

    expect(result).toEqual(payload);
    expect(calls[0]!.url).toBe('/api/transcription-keys');
    expect(calls[0]!.init.method).toBe('POST');
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
      secret_id: 'secret-1',
      label: 'ma clé deepgram',
      workers_count: 2,
    });
  });

  it('updateKey envoie PATCH avec body workers_count', async () => {
    const payload = { id: 'key-1', workers_count: 3 };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await updateKey('key-1', { workers_count: 3 });

    expect(result).toEqual(payload);
    expect(calls[0]!.url).toBe('/api/transcription-keys/key-1');
    expect(calls[0]!.init.method).toBe('PATCH');
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ workers_count: 3 });
  });

  it('testKey envoie POST sur /api/transcription-keys/{id}/test', async () => {
    const payload = { status: 'active', last_validated_at: null, balance_usd: 12.5, error: null };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await testKey('key-1');

    expect(result).toEqual(payload);
    expect(calls[0]!.url).toBe('/api/transcription-keys/key-1/test');
    expect(calls[0]!.init.method).toBe('POST');
  });

  it('updateQuota envoie PATCH avec monthly_cap_usd=50', async () => {
    const payload = { id: 'key-1', monthly_cap_usd: 50 };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await updateQuota('key-1', 50);

    expect(result).toEqual(payload);
    expect(calls[0]!.url).toBe('/api/transcription-keys/key-1/quota');
    expect(calls[0]!.init.method).toBe('PATCH');
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ monthly_cap_usd: 50 });
  });

  it('updateQuota avec null sérialise monthly_cap_usd: null', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ id: 'key-1', monthly_cap_usd: null }) });
    globalThis.fetch = fn;

    await updateQuota('key-1', null);

    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ monthly_cap_usd: null });
  });

  it('getUsage envoie GET sur /api/transcription-keys/{id}/usage', async () => {
    const payload = {
      current_month_spend_usd: 4.2,
      monthly_cap_usd: 50,
      pct_used: 8.4,
      last_balance_check_at: null,
      current_balance_usd: null,
    };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await getUsage('key-1');

    expect(result).toEqual(payload);
    expect(calls[0]!.url).toBe('/api/transcription-keys/key-1/usage');
    expect(calls[0]!.init.method).toBeUndefined();
  });

  it('deleteKey envoie DELETE sur /api/transcription-keys/{id}', async () => {
    const { calls, fn } = mockFetch({ status: 204, json: async () => undefined });
    globalThis.fetch = fn;

    await deleteKey('key-1');

    expect(calls[0]!.url).toBe('/api/transcription-keys/key-1');
    expect(calls[0]!.init.method).toBe('DELETE');
  });
});
