/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Pas de rewrite /api/* → backend : entre en conflit avec /api/auth/* géré par
  // Auth.js (Next.js applique la rewrite avant de chercher le route handler dynamic
  // de [...nextauth], malgré afterFiles).
  //
  // Stratégie actuelle :
  // - SSR (Server Components) appellent le backend via process.env.BACKEND_INTERNAL_URL
  //   (= http://backend:8000 dans le réseau Docker compose).
  // - Côté client, les fetch passent par NEXT_PUBLIC_API_URL avec un Bearer token
  //   (helper apiFetchWithToken). Si le backend doit être joignable depuis un browser
  //   distant (production via Cloudflare Tunnel), exposer un sous-domaine dédié
  //   api-role-agflow.yoops.org → backend:8000 dans le tunnel.
  experimental: {
    instrumentationHook: true,
  },
  webpack: (config, { nextRuntime }) => {
    if (nextRuntime === 'nodejs') {
      // Bundle Node.js serveur : crypto est un built-in, le marquer external
      // pour que webpack émette require('crypto') plutôt que de tenter de le bundler.
      const existing = config.externals;
      config.externals = [
        { crypto: 'commonjs crypto' },
        ...(Array.isArray(existing) ? existing : existing ? [existing] : []),
      ];
    } else {
      // Bundle Edge ou client : pas de built-ins Node.js.
      // vault.ts ne s'exécute jamais dans ces contextes (guard NEXT_RUNTIME).
      config.resolve.fallback = { ...config.resolve.fallback, crypto: false };
    }
    return config;
  },
};

module.exports = nextConfig;
