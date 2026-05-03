import { api } from './client';
import type {
  KeyUsage,
  TestKeyResult,
  TranscriptionKey,
  TranscriptionProvider,
} from '../types';

export async function listKeys(): Promise<TranscriptionKey[]> {
  return api<TranscriptionKey[]>('/api/transcription-keys');
}

export async function createKey(body: {
  provider: TranscriptionProvider;
  label?: string | null;
  api_key: string;
  harpocrate_key: string;
  workers_count?: number;
  is_primary?: boolean;
  is_fallback?: boolean;
}): Promise<TranscriptionKey> {
  return api<TranscriptionKey>('/api/transcription-keys', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function updateKey(
  id: string,
  body: {
    workers_count?: number;
    is_primary?: boolean;
    is_fallback?: boolean;
  },
): Promise<TranscriptionKey> {
  return api<TranscriptionKey>(`/api/transcription-keys/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function testKey(id: string): Promise<TestKeyResult> {
  return api<TestKeyResult>(`/api/transcription-keys/${id}/test`, {
    method: 'POST',
  });
}

export async function updateQuota(
  id: string,
  monthlyCap: number | null,
): Promise<TranscriptionKey> {
  return api<TranscriptionKey>(`/api/transcription-keys/${id}/quota`, {
    method: 'PATCH',
    body: JSON.stringify({ monthly_cap_usd: monthlyCap }),
  });
}

export async function getUsage(id: string): Promise<KeyUsage> {
  return api<KeyUsage>(`/api/transcription-keys/${id}/usage`);
}

export async function deleteKey(id: string): Promise<void> {
  await api<void>(`/api/transcription-keys/${id}`, { method: 'DELETE' });
}
