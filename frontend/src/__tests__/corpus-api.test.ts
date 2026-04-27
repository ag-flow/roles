import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  searchCorpus,
  listChunks,
  getAudioUrl,
  getTranscript,
} from '@/lib/api/corpus';

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

describe('corpus API client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('searchCorpus encode q et passe limit', async () => {
    const payload = {
      query: 'hello world',
      results: [
        {
          chunk_id: 'c-1',
          source_item_id: 'i-1',
          source_title: 'Vidéo 1',
          text: 'Bonjour le monde',
          start_s: 0,
          end_s: 12.5,
          similarity: 0.92,
        },
      ],
    };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await searchCorpus('rp-1', 'hello world');

    expect(result).toEqual(payload);
    expect(calls).toHaveLength(1);
    const call = calls[0]!;
    expect(call.url).toBe(
      'http://localhost:8000/api/role-projects/rp-1/corpus/search?q=hello%20world&limit=20',
    );
    expect(call.init.method).toBeUndefined();
  });

  it('searchCorpus respecte un limit custom', async () => {
    const { calls, fn } = mockFetch({
      json: async () => ({ query: 'q', results: [] }),
    });
    globalThis.fetch = fn;

    await searchCorpus('rp-1', 'q', 5);

    expect(calls[0]!.url).toBe(
      'http://localhost:8000/api/role-projects/rp-1/corpus/search?q=q&limit=5',
    );
  });

  it('listChunks construit les query params', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;

    await listChunks('rp-1', {
      source_item_id: 'i-1',
      limit: 50,
      offset: 10,
    });

    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe(
      'http://localhost:8000/api/role-projects/rp-1/corpus/chunks?source_item_id=i-1&limit=50&offset=10',
    );
  });

  it('listChunks sans options ne pose pas de query string', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;

    await listChunks('rp-1');

    expect(calls[0]!.url).toBe('http://localhost:8000/api/role-projects/rp-1/corpus/chunks');
  });

  it('getAudioUrl appelle la bonne route', async () => {
    const payload = { item_id: 'i-1', url: 'https://s3.example/foo', expires_in_s: 3600 };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await getAudioUrl('rp-1', 'i-1');

    expect(result).toEqual(payload);
    expect(calls[0]!.url).toBe(
      'http://localhost:8000/api/role-projects/rp-1/corpus/items/i-1/audio-url',
    );
  });

  it('getTranscript renvoie le pivot', async () => {
    const payload = {
      item_id: 'i-1',
      s3_key: 'transcripts/i-1.json',
      pivot: { segments: [{ start: 0, end: 1.5, text: 'Bonjour' }] },
    };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await getTranscript('rp-1', 'i-1');

    expect(result).toEqual(payload);
    expect(calls[0]!.url).toBe(
      'http://localhost:8000/api/role-projects/rp-1/corpus/items/i-1/transcript',
    );
  });
});
