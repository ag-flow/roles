import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as github from '@/lib/api/github';

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

describe('github API client', () => {
  const origFetch = globalThis.fetch;
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    globalThis.fetch = origFetch;
  });

  it('getStatus GET /auth/github/status', async () => {
    const { calls, fn } = mockFetch({
      json: async () => ({
        connected: false, github_login: null, scope: null, last_validated_at: null,
      }),
    });
    globalThis.fetch = fn;
    await github.getStatus();
    expect(calls[0]!.url).toBe(
      '/api/auth/github/status',
    );
  });

  it('startOAuth GET /auth/github/start', async () => {
    const { calls, fn } = mockFetch({
      json: async () => ({ redirect_url: 'https://github.com/...' }),
    });
    globalThis.fetch = fn;
    await github.startOAuth();
    expect(calls[0]!.url).toBe(
      '/api/auth/github/start',
    );
  });

  it('disconnect DELETE /auth/github', async () => {
    const { calls, fn } = mockFetch({
      json: async () => ({ status: 'disconnected' }),
    });
    globalThis.fetch = fn;
    await github.disconnect();
    expect(calls[0]!.url).toBe('/api/auth/github');
    expect(calls[0]!.init.method).toBe('DELETE');
  });

  it('listRepos GET /github/repos', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;
    await github.listRepos();
    expect(calls[0]!.url).toBe('/api/github/repos');
  });

  it('getPublicationConfig retourne null sur 404', async () => {
    const { fn } = mockFetch({
      ok: false,
      status: 404,
      text: async () => 'Not Found',
    });
    globalThis.fetch = fn;
    const result = await github.getPublicationConfig('rp-1');
    expect(result).toBeNull();
  });

  it('getPublicationConfig propage les autres erreurs', async () => {
    const { fn } = mockFetch({
      ok: false,
      status: 500,
      text: async () => 'Server error',
    });
    globalThis.fetch = fn;
    await expect(github.getPublicationConfig('rp-1')).rejects.toThrow();
  });

  it('setPublicationConfig PUT avec body license_choice', async () => {
    const { calls, fn } = mockFetch({
      json: async () => ({ status: 'saved' }),
    });
    globalThis.fetch = fn;
    await github.setPublicationConfig('rp-1', {
      repo_full_name: 'a/r',
      target_subdirectory: 'x',
      license_choice: 'mit',
    });
    expect(calls[0]!.url).toBe(
      '/api/role-projects/rp-1/publication-config',
    );
    expect(calls[0]!.init.method).toBe('PUT');
    expect(calls[0]!.init.body).toBe(
      JSON.stringify({
        repo_full_name: 'a/r',
        target_subdirectory: 'x',
        license_choice: 'mit',
      }),
    );
  });

  it('publishToGithub POST /publish-to-github', async () => {
    const { calls, fn } = mockFetch({
      json: async () => ({ commit_sha: 'x', url: 'y', files_count: 5 }),
    });
    globalThis.fetch = fn;
    await github.publishToGithub('rp-1');
    expect(calls[0]!.url).toBe(
      '/api/role-projects/rp-1/publish-to-github',
    );
    expect(calls[0]!.init.method).toBe('POST');
  });

  it('unpublishFromGithub DELETE /github-publication', async () => {
    const { calls, fn } = mockFetch({
      json: async () => ({ deleted_files: 3 }),
    });
    globalThis.fetch = fn;
    await github.unpublishFromGithub('rp-1');
    expect(calls[0]!.url).toBe(
      '/api/role-projects/rp-1/github-publication',
    );
    expect(calls[0]!.init.method).toBe('DELETE');
  });

  it('listPublications GET /publications', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;
    await github.listPublications('rp-1');
    expect(calls[0]!.url).toBe(
      '/api/role-projects/rp-1/publications',
    );
  });

  it('repoBrowseUrl construit l\'URL GitHub tree', () => {
    expect(github.repoBrowseUrl('alice/roles', 'main')).toBe(
      'https://github.com/alice/roles/tree/main',
    );
  });
});
