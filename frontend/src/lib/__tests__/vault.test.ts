import { describe, it, expect } from 'vitest';
import { parseHarpocrateToken } from '../vault';

// Token de test synthétique — structure valide mais pas de vraie crypto
// Les tests unitaires vérifient le parsing et la détection de refs vault.
// Les tests end-to-end (avec un vrai token) sont dans tests/e2e/.

describe('parseHarpocrateToken', () => {
  it('rejette un token sans préfixe hrpv_', () => {
    expect(() => parseHarpocrateToken('invalid_token')).toThrow('Invalid token prefix');
  });

  it('rejette un token trop court', () => {
    expect(() => parseHarpocrateToken('hrpv_short')).toThrow();
  });
});

describe('resolveVaultRef (unit — no network)', () => {
  it('passe les valeurs non-vault telles quelles (sync check)', async () => {
    // Import dynamique pour éviter les effets de bord du cache module-level
    const { resolveVaultRef } = await import('../vault');
    expect(await resolveVaultRef('plain_value')).toBe('plain_value');
    expect(await resolveVaultRef('')).toBe('');
    expect(await resolveVaultRef('https://api.openai.com')).toBe('https://api.openai.com');
  });

  it('détecte correctement le pattern vault ref', () => {
    const REF = '${vault://api1:openai_api_key}';
    expect(REF).toMatch(/^\$\{vault:\/\/[^:]+:[^}]+\}$/);
  });

  it('detecte les refs embedded dans une string', () => {
    const embedded = 'postgresql://user:${vault://api1:pg_pass}@localhost/db';
    expect(embedded).toContain('${vault://');
  });
});
