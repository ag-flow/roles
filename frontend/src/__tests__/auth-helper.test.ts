import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';
import { apiFetchWithToken } from '@/lib/api/client';

type FetchArgs = Parameters<typeof fetch>;
type FetchMock = Mock<FetchArgs, Promise<Response>>;

describe('apiFetchWithToken', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function mockOkFetch(): FetchMock {
    const impl: typeof fetch = async () =>
      ({
        ok: true,
        status: 200,
        json: async () => ({ ok: true }),
      }) as Response;
    return vi.fn(impl);
  }

  function lastCallInit(fetchMock: FetchMock): RequestInit {
    const calls = fetchMock.mock.calls;
    expect(calls.length).toBeGreaterThan(0);
    const callArgs = calls[0];
    if (!callArgs || callArgs.length < 2) {
      throw new Error('fetch was called without an init argument');
    }
    return callArgs[1] as RequestInit;
  }

  it('injecte Authorization Bearer si accessToken fourni', async () => {
    const fetchMock = mockOkFetch();
    globalThis.fetch = fetchMock;

    await apiFetchWithToken('/api/me', 'tok-abc-123');

    const headers = new Headers(lastCallInit(fetchMock).headers);
    expect(headers.get('Authorization')).toBe('Bearer tok-abc-123');
  });

  it("n'injecte pas Authorization si accessToken=undefined", async () => {
    const fetchMock = mockOkFetch();
    globalThis.fetch = fetchMock;

    await apiFetchWithToken('/api/public', undefined);

    const headers = new Headers(lastCallInit(fetchMock).headers);
    expect(headers.has('Authorization')).toBe(false);
  });

  it('set Content-Type: application/json si body présent et pas de Content-Type', async () => {
    const fetchMock = mockOkFetch();
    globalThis.fetch = fetchMock;

    await apiFetchWithToken('/api/things', 'tok', {
      method: 'POST',
      body: JSON.stringify({ x: 1 }),
    });

    const headers = new Headers(lastCallInit(fetchMock).headers);
    expect(headers.get('Content-Type')).toBe('application/json');
  });
});
