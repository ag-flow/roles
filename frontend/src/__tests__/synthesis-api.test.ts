import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  triggerExtraction,
  triggerDocumentWriting,
  triggerFullPipeline,
  regenerateDocument,
  setCurrentVersion,
  triggerClustering,
  triggerDecomposition,
  triggerIdentitySynthesis,
} from '@/lib/api/synthesis';
import { listRuns, getRun } from '@/lib/api/runs';

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

describe('synthesis API client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('triggerExtraction envoie POST sur la bonne URL avec body JSON', async () => {
    const payload = { run_id: 'run-1' };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await triggerExtraction('rp-1', { chunks_per_batch: 50 });

    expect(result).toEqual(payload);
    expect(calls).toHaveLength(1);
    const call = calls[0]!;
    expect(call.url).toBe('http://localhost:8000/api/role-projects/rp-1/runs/extract');
    expect(call.init.method).toBe('POST');
    expect(JSON.parse(String(call.init.body))).toEqual({ chunks_per_batch: 50 });
  });

  it('triggerDocumentWriting envoie plan_id + parallelism dans le body', async () => {
    const payload = { run_ids: ['run-1', 'run-2'] };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await triggerDocumentWriting('rp-1', 'plan-42', 5);

    expect(result).toEqual(payload);
    expect(calls).toHaveLength(1);
    const call = calls[0]!;
    expect(call.url).toBe(
      'http://localhost:8000/api/role-projects/rp-1/runs/write-documents',
    );
    expect(call.init.method).toBe('POST');
    expect(JSON.parse(String(call.init.body))).toEqual({
      plan_id: 'plan-42',
      parallelism: 5,
    });
  });

  it('triggerDocumentWriting utilise parallelism=3 par défaut', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ run_ids: [] }) });
    globalThis.fetch = fn;

    await triggerDocumentWriting('rp-1', 'plan-1');

    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
      plan_id: 'plan-1',
      parallelism: 3,
    });
  });

  it('regenerateDocument envoie instruction_override', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ run_id: 'run-2' }) });
    globalThis.fetch = fn;

    await regenerateDocument('doc-1', 'Sois plus concis');

    const call = calls[0]!;
    expect(call.url).toBe('http://localhost:8000/api/role-documents/doc-1/regenerate');
    expect(call.init.method).toBe('POST');
    expect(JSON.parse(String(call.init.body))).toEqual({
      instruction_override: 'Sois plus concis',
    });
  });

  it('regenerateDocument envoie null si instruction_override absent', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ run_id: 'run-3' }) });
    globalThis.fetch = fn;

    await regenerateDocument('doc-2');

    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
      instruction_override: null,
    });
  });

  it('setCurrentVersion envoie POST sans body', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ status: 'ok' }) });
    globalThis.fetch = fn;

    const result = await setCurrentVersion('doc-3');

    expect(result).toEqual({ status: 'ok' });
    const call = calls[0]!;
    expect(call.url).toBe('http://localhost:8000/api/role-documents/doc-3/set-current');
    expect(call.init.method).toBe('POST');
  });

  it('triggerClustering envoie POST avec signal_run_id', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ run_id: 'run-4' }) });
    globalThis.fetch = fn;

    await triggerClustering('rp-1', { signal_run_id: 'run-0' });

    expect(calls[0]!.url).toBe(
      'http://localhost:8000/api/role-projects/rp-1/runs/cluster',
    );
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ signal_run_id: 'run-0' });
  });

  it('triggerDecomposition envoie POST avec cluster_run_id', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ run_id: 'run-5' }) });
    globalThis.fetch = fn;

    await triggerDecomposition('rp-1', { cluster_run_id: 'run-2' });

    expect(calls[0]!.url).toBe(
      'http://localhost:8000/api/role-projects/rp-1/runs/decompose',
    );
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
      cluster_run_id: 'run-2',
    });
  });

  it('triggerIdentitySynthesis envoie POST avec instruction_override', async () => {
    const { calls, fn } = mockFetch({ json: async () => ({ run_id: 'run-6' }) });
    globalThis.fetch = fn;

    await triggerIdentitySynthesis('rp-1', { instruction_override: 'Override' });

    expect(calls[0]!.url).toBe(
      'http://localhost:8000/api/role-projects/rp-1/runs/synthesize-identity',
    );
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
      instruction_override: 'Override',
    });
  });
});

describe('runs API client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('listRuns construit la querystring avec status et limit', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;

    await listRuns('rp-1', { status: 'done', limit: 10 });

    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe(
      'http://localhost:8000/api/role-projects/rp-1/runs?status=done&limit=10',
    );
    expect(calls[0]!.init.method).toBeUndefined();
  });

  it('listRuns sans options ne pose pas de querystring', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;

    await listRuns('rp-1');

    expect(calls[0]!.url).toBe('http://localhost:8000/api/role-projects/rp-1/runs');
  });

  it('listRuns avec status seulement', async () => {
    const { calls, fn } = mockFetch({ json: async () => [] });
    globalThis.fetch = fn;

    await listRuns('rp-1', { status: 'running' });

    expect(calls[0]!.url).toBe(
      'http://localhost:8000/api/role-projects/rp-1/runs?status=running',
    );
  });

  it('getRun envoie GET sur /api/runs/{id}', async () => {
    const payload = {
      id: 'run-99',
      role_project_id: 'rp-1',
      prompt_version_id: 'pv-1',
      status: 'done',
      output: 'résultat',
      llm_provider: 'mistral',
      llm_model: 'mistral-large',
      tokens_input: 1000,
      tokens_output: 500,
      cost_usd: 0.02,
      instruction_override: null,
      started_at: '2026-01-01T00:00:00Z',
      completed_at: '2026-01-01T00:01:00Z',
      error: null,
      created_at: '2026-01-01T00:00:00Z',
    };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await getRun('run-99');

    expect(result).toEqual(payload);
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe('http://localhost:8000/api/runs/run-99');
    expect(calls[0]!.init.method).toBeUndefined();
  });

  it('triggerFullPipeline POST avec le body complet', async () => {
    const payload = {
      extract_run_id: 'r1',
      cluster_run_id: 'r2',
      decompose_run_id: 'r3',
      document_run_ids: ['r4', 'r5', 'r6'],
      identity_run_id: 'r7',
    };
    const { calls, fn } = mockFetch({ json: async () => payload });
    globalThis.fetch = fn;

    const result = await triggerFullPipeline('rp-1', {
      chunks_per_batch: 8,
      parallelism: 2,
      include_identity: true,
    });

    expect(result).toEqual(payload);
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe(
      'http://localhost:8000/api/role-projects/rp-1/runs/full-pipeline',
    );
    expect(calls[0]!.init.method).toBe('POST');
    expect(calls[0]!.init.body).toBe(
      JSON.stringify({
        chunks_per_batch: 8,
        parallelism: 2,
        include_identity: true,
      }),
    );
  });

  it('triggerFullPipeline avec body vide envoie {}', async () => {
    const { calls, fn } = mockFetch({
      json: async () => ({
        extract_run_id: 'a',
        cluster_run_id: 'b',
        decompose_run_id: 'c',
        document_run_ids: [],
        identity_run_id: null,
      }),
    });
    globalThis.fetch = fn;
    await triggerFullPipeline('rp-1');
    expect(calls[0]!.init.body).toBe('{}');
  });
});
