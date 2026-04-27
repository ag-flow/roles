/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // afterFiles : Next.js cherche d'abord dans le filesystem (app/api/auth/...
    // pour Auth.js) AVANT d'appliquer le rewrite. Donc /api/auth/* reste géré
    // par Next.js, le reste de /api/* est proxifié vers le backend.
    // Bug fix Sprint 2 : destination cible /api/... (le backend FastAPI a ses
    // routes sous /api/, il faut conserver le préfixe).
    return {
      afterFiles: [
        {
          source: '/api/:path*',
          destination: `${process.env.BACKEND_INTERNAL_URL || 'http://localhost:8000'}/api/:path*`,
        },
      ],
    };
  },
};

module.exports = nextConfig;
