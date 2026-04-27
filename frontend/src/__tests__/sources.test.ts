import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  createSource,
  discoverSource,
  listItems,
  selectItems,
} from '@/lib/api/sources';
import { ApiError } from '@/lib/api/client';

interface FetchCall {
  url: string;
  init: RequestInit;
}

function mockFetch(response: Partial<Response> & { json?: () => Promise<unknown>; text?: () => Promise<string> }): {
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

describe('sources API client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('createSource POST le body et renvoie la source', async () => {
    const sourcePayload = {
      id: 'src-1',
      role_project_id: 'rp-1',
      platform: 'youtube',
      source_type: 'channel',
      url: 'https://youtube.com/@x',
      status: 'pending_discovery',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    const { calls, fn } = mockFetch({ json: async () => sourcePayload });
    globalThis.fetch = fn;

    const result = await createSource('rp-1', {
      url: 'https://youtube.com/@x',
      platform: 'youtube',
      source_type: 'channel',
    });

    expect(result).toEqual(sourcePayload);
    expect(calls).toHaveLength(1);
    const call = calls[0]!;
    expect(call.url).toBe('http://localhost:8000/api/role-projects/rp-1/sources');
    expect(call.init.method).toBe('POST');
    expect(JSON.parse(String(call.init.body))).toEqual({
      url: 'https://youtube.com/@x',
      platform: 'youtube',
      source_type: 'channel',
    });
  });

  it('discoverSource POST sans body', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ job_id: 'j-1' }) });
    globalThis.fetch = fn;

    const result = await discoverSource('src-1');

    expect(result).toEqual({ job_id: 'j-1' });
    expect(calls).toHaveLength(1);
    const call = calls[0]!;
    expect(call.url).toBe('http://localhost:8000/api/sources/src-1/discover');
    expect(call.init.method).toBe('POST');
    expect(call.init.body).toBeUndefined();
  });

  it('listItems construit les query params correctement', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;

    await listItems('src-1', {
      min_duration_s: 60,
      since_date: '2026-01-01',
      status: 'pending_download',
      selected: true,
      limit: 50,
      offset: 10,
    });

    expect(calls).toHaveLength(1);
    const call = calls[0]!;
    expect(call.url).toBe(
      'http://localhost:8000/api/sources/src-1/items?min_duration_s=60&since_date=2026-01-01&status=pending_download&selected=true&limit=50&offset=10',
    );
  });

  it('listItems sans filtres ne pose pas de query string', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;

    await listItems('src-1');

    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe('http://localhost:8000/api/sources/src-1/items');
  });

  it('selectItems POST le body et renvoie le résultat', async () => {
    const { calls, fn } = mockFetch({
      json: async () => ({ selected_count: 2, jobs_created: 2 }),
    });
    globalThis.fetch = fn;

    const result = await selectItems('src-1', {
      item_ids: ['a', 'b'],
      deselect_others: true,
    });

    expect(result).toEqual({ selected_count: 2, jobs_created: 2 });
    const call = calls[0]!;
    expect(call.url).toBe('http://localhost:8000/api/sources/src-1/items/select');
    expect(call.init.method).toBe('POST');
    expect(JSON.parse(String(call.init.body))).toEqual({
      item_ids: ['a', 'b'],
      deselect_others: true,
    });
  });

  it('jette ApiError sur réponse 4xx', async () => {
    const { fn } = mockFetch({
      ok: false,
      status: 422,
      text: async () => 'invalid url',
    });
    globalThis.fetch = fn;

    await expect(
      createSource('rp-1', {
        url: 'bad',
        platform: 'youtube',
        source_type: 'channel',
      }),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
