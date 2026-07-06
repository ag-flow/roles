import { api } from './client';

export type SecretType =
  | 'openai-whisper'
  | 'deepgram'
  | 'assemblyai'
  | 'speechmatics'
  | 'youtube-cookies'
  | 'instagram-cookies'
  | 'tiktok-cookies';

export type SecretStorage = 'local' | 'wallet';

export type SecretStatus = 'active' | 'invalid' | 'revoked';

export interface Secret {
  id: string;
  secret_type: SecretType;
  label: string;
  storage: SecretStorage;
  wallet_id: string | null;
  status: SecretStatus;
  created_at: string;
}

export const SECRET_TYPE_LABELS: Record<SecretType, string> = {
  'openai-whisper': 'OpenAI Whisper',
  deepgram: 'Deepgram',
  assemblyai: 'AssemblyAI',
  speechmatics: 'Speechmatics',
  'youtube-cookies': 'Cookies YouTube',
  'instagram-cookies': 'Cookies Instagram',
  'tiktok-cookies': 'Cookies TikTok',
};

export const TRANSCRIPTION_SECRET_TYPES: SecretType[] = [
  'openai-whisper',
  'deepgram',
  'assemblyai',
  'speechmatics',
];

export async function listSecrets(secretType?: SecretType): Promise<Secret[]> {
  const qs = secretType ? `?secret_type=${secretType}` : '';
  return api<Secret[]>(`/api/secrets${qs}`);
}

export async function createSecret(body: {
  secret_type: SecretType;
  label: string;
  value: string;
  wallet_id?: string | null;
}): Promise<Secret> {
  return api<Secret>('/api/secrets', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function deleteSecret(id: string): Promise<void> {
  await api<void>(`/api/secrets/${id}`, { method: 'DELETE' });
}
