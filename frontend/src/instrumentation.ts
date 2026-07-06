/**
 * Next.js instrumentation hook — plus rien à faire au démarrage depuis la
 * refonte self-service (2026-07-05) : les indirections ${vault://} du .env
 * ne sont plus supportées, tous les secrets machine sont des valeurs planes.
 * Le hook garde-fou refuse de démarrer si un ancien .env en porte encore.
 */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== 'nodejs') return;

  const stale = Object.entries(process.env).filter(
    ([, v]) => v && v.includes('${vault://'),
  );
  if (stale.length > 0) {
    console.error(
      '[env] FATAL: indirections ${vault://} obsolètes détectées dans le .env',
      `(${stale.map(([k]) => k).join(', ')}) — relancer dev-deploy.sh pour régénérer.`,
    );
    process.exit(1);
  }
}
