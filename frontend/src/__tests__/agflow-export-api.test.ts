import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  previewZip,
  pushToAgflow,
  generatePromptsOnAgflow,
  downloadZipUrl,
} from '@/lib/api/agflow-export';

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

describe('agflow-export API client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('previewZip GET le bon path et renvoie le payload', async () => {
    const payload = {
      display_name: 'Agent X',
      description: null,
      identity_length: 1500,
      target_role_id: null,
      sections: [
        { name: 'Role', documents: [{ name: 'principe', size: 1200 }] },
      ],
      ready_to_push: true,
      missing: [],
    };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await previewZip('rp-1');

    expect(result).toEqual(payload);
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe(
      '/api/role-projects/rp-1/preview-zip',
    );
    expect(calls[0]!.init.method).toBeUndefined();
  });

  it('pushToAgflow POST avec body generate_prompts', async () => {
    const payload = {
      agflow_role_id: 'r-abc',
      zip_size_bytes: 12345,
      documents_count: 7,
      prompt_generated: true,
      agflow_url: 'https://docker-agflow.yoops.org/admin/roles/r-abc',
    };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await pushToAgflow('rp-1', { generate_prompts: true });

    expect(result).toEqual(payload);
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe(
      '/api/role-projects/rp-1/push-to-agflow',
    );
    expect(calls[0]!.init.method).toBe('POST');
    expect(calls[0]!.init.body).toBe(JSON.stringify({ generate_prompts: true }));
  });

  it('generatePromptsOnAgflow POST sans body', async () => {
    const payload = { status: 'generated', target_role_id: 'r-abc' };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await generatePromptsOnAgflow('rp-1');

    expect(result).toEqual(payload);
    expect(calls[0]!.url).toBe(
      '/api/role-projects/rp-1/generate-prompts-on-agflow',
    );
    expect(calls[0]!.init.method).toBe('POST');
  });

  it('downloadZipUrl construit l\'URL absolue (pour <a href=...>)', () => {
    expect(downloadZipUrl('rp-1')).toBe(
      '/api/role-projects/rp-1/download-zip',
    );
  });
});
