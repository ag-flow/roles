import { api } from './client';
import type {
  Chunk,
  SearchResponse,
  AudioUrlResponse,
  TranscriptResponse,
} from '../types';

export async function searchCorpus(
  projectId: string,
  q: string,
  limit = 20,
): Promise<SearchResponse> {
  return api(
    `/api/role-projects/${projectId}/corpus/search?q=${encodeURIComponent(q)}&limit=${limit}`,
  );
}

export async function listChunks(
  projectId: string,
  opts: { source_item_id?: string; limit?: number; offset?: number } = {},
): Promise<Chunk[]> {
  const qs = new URLSearchParams();
  if (opts.source_item_id) qs.set('source_item_id', opts.source_item_id);
  if (opts.limit !== undefined) qs.set('limit', String(opts.limit));
  if (opts.offset !== undefined) qs.set('offset', String(opts.offset));
  const path = `/api/role-projects/${projectId}/corpus/chunks${
    qs.toString() ? '?' + qs.toString() : ''
  }`;
  return api(path);
}

export async function getAudioUrl(
  projectId: string,
  itemId: string,
): Promise<AudioUrlResponse> {
  return api(`/api/role-projects/${projectId}/corpus/items/${itemId}/audio-url`);
}

export async function getTranscript(
  projectId: string,
  itemId: string,
): Promise<TranscriptResponse> {
  return api(`/api/role-projects/${projectId}/corpus/items/${itemId}/transcript`);
}

export async function rebuildCorpus(
  projectId: string,
): Promise<{ deleted_chunks: number; enqueued_jobs: number }> {
  return api(`/api/role-projects/${projectId}/corpus/rebuild`, {
    method: 'POST',
  });
}
