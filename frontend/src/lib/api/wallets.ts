import { api } from './client';

export type WalletStatus = 'active' | 'invalid' | 'revoked';

export interface Wallet {
  id: string;
  label: string;
  api_url: string;
  status: WalletStatus;
  created_at: string;
}

export async function listWallets(): Promise<Wallet[]> {
  return api<Wallet[]>('/api/wallets');
}

export async function createWallet(body: {
  label: string;
  api_token: string;
  api_url?: string;
}): Promise<Wallet> {
  return api<Wallet>('/api/wallets', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function deleteWallet(id: string): Promise<void> {
  await api<void>(`/api/wallets/${id}`, { method: 'DELETE' });
}
