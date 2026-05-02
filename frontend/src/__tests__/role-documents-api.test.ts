import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  listRoleDocumentsGrouped,
  getRoleDocument,
  listRoleDocumentVersions,
  updateRoleDocumentContent,
  lockRoleDocument,
  unlockRoleDocument,
  setCurrentRoleDocument,
  regenerateRoleDocument,
} from '@/lib/api/role-documents';

interface FetchCall {
  url: string;
  init: RequestInit;
}

function mockFetch(
  response: Partial<Response> & {
    json?: () => Promise<unknown>;
    text?: () => Promise<string>;
  },
): { calls: FetchCall[]; fn: typeof globalThis.fetch } {
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

describe('role-documents API client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('listRoleDocumentsGrouped GET la liste groupée', async () => {
    const payload = {
      sections: {
        Role: [
          {
            id: 'd1',
            section: 'Role',
            name: 'principe',
            version: 1,
            is_current: true,
            locked: false,
            updated_at: '2026-04-29T10:00:00Z',
          },
        ],
        Missions: [],
      },
    };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await listRoleDocumentsGrouped('rp-1');

    expect(result).toEqual(payload);
    expect(calls[0]!.url).toBe(
      '/api/role-projects/rp-1/role-documents',
    );
  });

  it('getRoleDocument GET le détail', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({}) });
    globalThis.fetch = fn;

    await getRoleDocument('d1');

    expect(calls[0]!.url).toBe('/api/role-documents/d1');
  });

  it('listRoleDocumentVersions GET versions', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;

    await listRoleDocumentVersions('d1');

    expect(calls[0]!.url).toBe(
      '/api/role-documents/d1/versions',
    );
  });

  it('updateRoleDocumentContent PATCH avec body content', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({}) });
    globalThis.fetch = fn;

    await updateRoleDocumentContent('d1', 'nouveau contenu');

    expect(calls[0]!.url).toBe('/api/role-documents/d1');
    expect(calls[0]!.init.method).toBe('PATCH');
    expect(calls[0]!.init.body).toBe(
      JSON.stringify({ content: 'nouveau contenu' }),
    );
  });

  it('lockRoleDocument POST /lock', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ status: 'locked' }) });
    globalThis.fetch = fn;

    await lockRoleDocument('d1');

    expect(calls[0]!.url).toBe('/api/role-documents/d1/lock');
    expect(calls[0]!.init.method).toBe('POST');
  });

  it('unlockRoleDocument POST /unlock', async () => {
    const { calls, fn } = mockFetch({
      json: async () => ({ status: 'unlocked' }),
    });
    globalThis.fetch = fn;

    await unlockRoleDocument('d1');

    expect(calls[0]!.url).toBe('/api/role-documents/d1/unlock');
    expect(calls[0]!.init.method).toBe('POST');
  });

  it('setCurrentRoleDocument POST /set-current', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ status: 'ok' }) });
    globalThis.fetch = fn;

    await setCurrentRoleDocument('d1');

    expect(calls[0]!.url).toBe(
      '/api/role-documents/d1/set-current',
    );
    expect(calls[0]!.init.method).toBe('POST');
  });

  it('regenerateRoleDocument POST /regenerate avec instruction_override', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ run_id: 'r1' }) });
    globalThis.fetch = fn;

    await regenerateRoleDocument('d1', 'plus formel');

    expect(calls[0]!.url).toBe(
      '/api/role-documents/d1/regenerate',
    );
    expect(calls[0]!.init.method).toBe('POST');
    expect(calls[0]!.init.body).toBe(
      JSON.stringify({ instruction_override: 'plus formel' }),
    );
  });

  it('regenerateRoleDocument POST /regenerate sans instruction (null)', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ run_id: 'r1' }) });
    globalThis.fetch = fn;

    await regenerateRoleDocument('d1');

    expect(calls[0]!.init.body).toBe(
      JSON.stringify({ instruction_override: null }),
    );
  });
});
