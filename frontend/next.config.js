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
};

module.exports = nextConfig;
