/**
 * Mini-client Harpocrate pour Next.js server-side (Node.js runtime).
 * Résout les références ${vault://id:key} depuis process.env via AES-256-GCM.
 *
 * Ne jamais importer dans le bundle client — server-side uniquement.
 */

import { createDecipheriv } from 'crypto';

const HMAC_LEN = 22;
const DKEY_LEN = 43;
const AUTH_LEN = 43;
const BASE32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

function base32Decode(str: string): Buffer {
  const s = str.toUpperCase().replace(/=/g, '');
  let bits = '';
  for (const ch of s) {
    const idx = BASE32_ALPHABET.indexOf(ch);
    if (idx === -1) throw new Error(`Invalid base32 char: ${ch}`);
    bits += idx.toString(2).padStart(5, '0');
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) {
    bytes.push(parseInt(bits.slice(i, i + 8), 2));
  }
  return Buffer.from(bytes);
}

function bytesToUuid(b: Buffer): string {
  const h = b.toString('hex');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

function aesGcmDecrypt(blob: Buffer, key: Buffer): Buffer {
  if (blob.length < 28) throw new Error('Blob too short for AES-GCM (min 28 bytes)');
  const nonce = blob.subarray(0, 12);
  const tag = blob.subarray(-16);
  const ciphertext = blob.subarray(12, -16);
  const decipher = createDecipheriv('aes-256-gcm', key, nonce);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]);
}

export interface ParsedToken {
  apiKeyId: string;
  decryptionKey: Buffer;
}

export function parseHarpocrateToken(token: string): ParsedToken {
  if (!token.startsWith('hrpv_')) {
    throw new Error('Invalid token prefix — must start with hrpv_');
  }

  const hmacB64 = token.slice(-HMAC_LEN);
  const dkeyB64 = token.slice(-(HMAC_LEN + 1 + DKEY_LEN), -(HMAC_LEN + 1));
  const authB64 = token.slice(
    -(HMAC_LEN + 1 + DKEY_LEN + 1 + AUTH_LEN),
    -(HMAC_LEN + 1 + DKEY_LEN + 1),
  );
  const prefixPart = token.slice(0, -(HMAC_LEN + 1 + DKEY_LEN + 1 + AUTH_LEN + 1));
  const parts = prefixPart.split('_');

  if (parts.length !== 5) {
    throw new Error(`Invalid token structure (expected 5 prefix parts, got ${parts.length})`);
  }

  const idB32 = parts[2];
  const expB36 = parts[3];
  if (!idB32 || !expB36) {
    throw new Error('Invalid token structure (missing id or expiry fields)');
  }
  const exp = parseInt(expB36, 36);
  if (exp !== 0 && exp < Math.floor(Date.now() / 1000)) {
    throw new Error('Harpocrate token has expired');
  }

  const dkeyBytes = Buffer.from(dkeyB64 + '==', 'base64url');
  if (dkeyBytes.length !== 32) {
    throw new Error(`Invalid decryption key length: ${dkeyBytes.length} (expected 32)`);
  }

  const idBytes = base32Decode(idB32);
  const apiKeyId = bytesToUuid(idBytes);

  void hmacB64;
  void authB64;

  return { apiKeyId, decryptionKey: dkeyBytes };
}

interface VaultClientState {
  baseUrl: string;
  token: string;
  parsed: ParsedToken;
  walletId?: string;
  walletKey?: Buffer;
}

let _clientState: VaultClientState | null = null;
const _secretCache = new Map<string, string>();

function _getClientState(): VaultClientState {
  if (_clientState) return _clientState;

  const token = process.env['HARPOCRATE_API_TOKEN'];
  const baseUrl = (process.env['HARPOCRATE_API_URL'] ?? 'https://vault.yoops.org').replace(/\/$/, '');

  if (!token) {
    throw new Error('No Harpocrate token — set HARPOCRATE_API_TOKEN');
  }

  const parsed = parseHarpocrateToken(token);
  _clientState = { baseUrl, token, parsed };
  return _clientState;
}

async function _vaultFetch(baseUrl: string, token: string, path: string): Promise<unknown> {
  const url = `${baseUrl}${path}`;
  const resp = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
    },
  });
  if (!resp.ok) {
    throw new Error(`Vault HTTP ${resp.status} on ${path}`);
  }
  return resp.json();
}

async function _getWalletId(state: VaultClientState): Promise<string> {
  if (state.walletId) return state.walletId;
  const data = await _vaultFetch(
    state.baseUrl,
    state.token,
    `/v1/api-keys/${state.parsed.apiKeyId}/wallet-id`,
  ) as { wallet_id: string };
  state.walletId = data.wallet_id;
  return data.wallet_id;
}

async function _getWalletKey(state: VaultClientState): Promise<Buffer> {
  if (state.walletKey) return state.walletKey;
  const walletId = await _getWalletId(state);
  const data = await _vaultFetch(
    state.baseUrl,
    state.token,
    `/v1/wallets/${walletId}/my-api-key-grant`,
  ) as { encrypted_wallet_key: string };
  const encWk = Buffer.from(data.encrypted_wallet_key, 'base64');
  const walletKey = aesGcmDecrypt(encWk, state.parsed.decryptionKey);
  state.walletKey = walletKey;
  return walletKey;
}

async function _fetchAndDecryptSecret(
  state: VaultClientState,
  secretName: string,
): Promise<string> {
  const walletId = await _getWalletId(state);
  const data = await _vaultFetch(
    state.baseUrl,
    state.token,
    `/v1/wallets/${walletId}/secrets/${secretName}`,
  ) as { encrypted_value: string; encrypted_wallet_key: string };

  const encValue = Buffer.from(data.encrypted_value, 'base64');

  try {
    const walletKey = await _getWalletKey(state);
    return aesGcmDecrypt(encValue, walletKey).toString('utf-8');
  } catch {
    // Fallback: use per-secret encrypted_wallet_key (for grant-based callers)
    const encWk = Buffer.from(data.encrypted_wallet_key, 'base64');
    const wkFromGrant = aesGcmDecrypt(encWk, state.parsed.decryptionKey);
    state.walletKey = wkFromGrant;
    return aesGcmDecrypt(encValue, wkFromGrant).toString('utf-8');
  }
}

const REF_RE = /\$\{vault:\/\/[^:}]+:([^}]+)\}/g;

export async function resolveVaultRef(value: string): Promise<string> {
  if (!value.includes('${vault://')) return value;

  const matches = [...value.matchAll(REF_RE)];
  if (matches.length === 0) return value;

  const state = _getClientState();
  let result = value;
  for (const m of matches) {
    const full = m[0];
    const secretName = m[1];
    if (!full || !secretName) continue;
    let secret = _secretCache.get(secretName);

    if (!secret) {
      secret = await _fetchAndDecryptSecret(state, secretName);
      _secretCache.set(secretName, secret);
    }

    result = result.replace(full, secret);
  }
  return result;
}

export async function resolveVaultEnv(): Promise<void> {
  const entries = Object.entries(process.env).filter(
    ([, v]) => v && v.includes('${vault://'),
  );

  if (entries.length === 0) return;

  const hasToken = Boolean(process.env['HARPOCRATE_API_TOKEN']);
  if (!hasToken) {
    throw new Error(
      'Vault refs found in env but HARPOCRATE_API_TOKEN is not set',
    );
  }

  for (const [key, ref] of entries) {
    try {
      process.env[key] = await resolveVaultRef(ref!);
    } catch (err) {
      throw new Error(
        `Harpocrate: failed to resolve ${key} — ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }
}
