/**
 * Next.js instrumentation hook — résout les références vault dans process.env
 * avant que les Route Handlers et Server Components ne soient servis.
 *
 * S'exécute une seule fois au démarrage du server Node.js.
 * Ne s'exécute PAS dans le runtime Edge (guard NEXT_RUNTIME === 'nodejs').
 */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== 'nodejs') return;

  const hasVaultRef = Object.values(process.env).some(
    (v) => v && v.includes('${vault://'),
  );
  if (!hasVaultRef) return;

  try {
    const { resolveVaultEnv } = await import('./lib/vault');
    await resolveVaultEnv();
    console.log('[vault] process.env patched — all vault refs resolved');
  } catch (err) {
    console.error('[vault] FATAL: failed to resolve vault secrets at startup:', err);
    process.exit(1);
  }
}
