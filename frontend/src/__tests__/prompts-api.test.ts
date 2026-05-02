import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { listPrompts, listVersions, createVersion, setSystemDefault } from '@/lib/api/prompts';

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

describe('prompts API client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('listPrompts envoie GET sur /api/prompts', async () => {
    const payload = [
      {
        id: 'p-1',
        name: 'extractor',
        type: 'extractor',
        target_section: null,
        description: 'Extrait les signaux',
      },
    ];
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await listPrompts();

    expect(result).toEqual(payload);
    expect(calls).toHaveLength(1);
    const call = calls[0]!;
    expect(call.url).toBe('/api/prompts');
    expect(call.init.method).toBeUndefined();
  });

  it('listVersions envoie GET sur /api/prompts/{id}/versions', async () => {
    const payload = [
      {
        id: 'pv-1',
        prompt_id: 'p-1',
        version_number: 1,
        template: 'Tu es un extracteur…',
        is_system_default: true,
        created_at: '2026-01-01T00:00:00Z',
      },
    ];
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await listVersions('p-1');

    expect(result).toEqual(payload);
    expect(calls).toHaveLength(1);
    const call = calls[0]!;
    expect(call.url).toBe('/api/prompts/p-1/versions');
    expect(call.init.method).toBeUndefined();
  });

  it('createVersion envoie POST avec body { template }', async () => {
    const payload = {
      id: 'pv-2',
      prompt_id: 'p-1',
      version_number: 2,
      template: 'Nouveau template',
      is_system_default: false,
      created_at: '2026-01-02T00:00:00Z',
    };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await createVersion('p-1', 'Nouveau template');

    expect(result).toEqual(payload);
    expect(calls).toHaveLength(1);
    const call = calls[0]!;
    expect(call.url).toBe('/api/prompts/p-1/versions');
    expect(call.init.method).toBe('POST');
    expect(JSON.parse(String(call.init.body))).toEqual({ template: 'Nouveau template' });
  });

  it('setSystemDefault envoie PUT sur /api/prompts/{id}/system-default/{vid}', async () => {
    const { calls, fn } = mockFetch({ status: 204, json: async () => undefined });
    globalThis.fetch = fn;

    await setSystemDefault('p-1', 'pv-2');

    expect(calls).toHaveLength(1);
    const call = calls[0]!;
    expect(call.url).toBe('/api/prompts/p-1/system-default/pv-2');
    expect(call.init.method).toBe('PUT');
  });

  it('listPrompts retourne un tableau vide si aucun prompt', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;

    const result = await listPrompts();

    expect(result).toEqual([]);
    expect(calls).toHaveLength(1);
  });
});
