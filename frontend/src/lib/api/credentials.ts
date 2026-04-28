import { api } from './client';
import type {
  CredentialPlatform,
  TestCredentialResult,
  UserCredential,
} from '../types';

export async function listCredentials(
  platform?: CredentialPlatform,
): Promise<UserCredential[]> {
  const qs = platform ? `?platform=${platform}` : '';
  return api<UserCredential[]>(`/api/credentials${qs}`);
}

export async function createCredential(body: {
  platform: CredentialPlatform;
  label?: string | null;
  cookies_b64: string;
}): Promise<UserCredential> {
  return api<UserCredential>('/api/credentials', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function testCredential(id: string): Promise<TestCredentialResult> {
  return api<TestCredentialResult>(`/api/credentials/${id}/test`, {
    method: 'POST',
  });
}

export async function deleteCredential(id: string): Promise<void> {
  await api<void>(`/api/credentials/${id}`, { method: 'DELETE' });
}
