import NextAuth from 'next-auth';
import type { Provider } from 'next-auth/providers';
import Credentials from 'next-auth/providers/credentials';
import Keycloak from 'next-auth/providers/keycloak';

declare module 'next-auth' {
  interface Session {
    accessToken?: string;
    refreshToken?: string;
    expiresAt?: number;
  }
  interface User {
    /** JWT issued par /api/auth/local-login (mode admin local). */
    accessToken?: string;
    expiresAt?: number;
  }
}

declare module '@auth/core/jwt' {
  interface JWT {
    accessToken?: string;
    refreshToken?: string;
    expiresAt?: number;
  }
}

/**
 * Mode admin local — auth sans OIDC.
 *
 * Activé via ``LOCAL_ADMIN_ENABLED=true``. Le provider Credentials envoie
 * (username, password) au backend ``POST /api/auth/local-login`` qui valide
 * contre le ``.env`` et retourne un JWT HS256 signé localement. Ce JWT est
 * stocké dans la session NextAuth et envoyé en Bearer pour les API calls,
 * exactement comme un JWT Keycloak.
 *
 * Utilité : permettre à un admin de se connecter sans Keycloak (dev, test,
 * environnements isolés). À désactiver en prod.
 */
const localAdminEnabled = process.env.LOCAL_ADMIN_ENABLED === 'true';

const backendInternalUrl =
  process.env.BACKEND_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://backend:8000';

const providers: Provider[] = [];

if (process.env.KEYCLOAK_ISSUER_URL) {
  providers.push(
    Keycloak({
      clientId: process.env.KEYCLOAK_CLIENT_ID!,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET!,
      issuer: process.env.KEYCLOAK_ISSUER_URL!,
    }),
  );
}

if (localAdminEnabled) {
  providers.push(
    Credentials({
      id: 'local-admin',
      name: 'Admin local',
      credentials: {
        username: { label: 'Identifiant', type: 'text' },
        password: { label: 'Mot de passe', type: 'password' },
      },
      authorize: async (creds) => {
        const username = String(creds?.username ?? '');
        const password = String(creds?.password ?? '');
        if (!username || !password) return null;

        try {
          const resp = await fetch(
            `${backendInternalUrl}/api/auth/local-login`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ username, password }),
              cache: 'no-store',
            },
          );
          if (!resp.ok) return null;
          const data = (await resp.json()) as {
            access_token: string;
            token_type: string;
            expires_in: number;
          };
          return {
            id: `local-admin:${username}`,
            name: username,
            email: `${username}@local`,
            accessToken: data.access_token,
            expiresAt:
              Math.floor(Date.now() / 1000) + Number(data.expires_in ?? 3600),
          };
        } catch {
          return null;
        }
      },
    }),
  );
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers,
  trustHost: true,
  session: { strategy: 'jwt' },
  callbacks: {
    async jwt({ token, account, user }) {
      // Login Keycloak — token attaché côté account.
      if (account?.access_token) {
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
        token.expiresAt = account.expires_at;
      }
      // Login Credentials (admin local) — token attaché côté user au premier
      // appel d'authorize() ; ensuite seuls token et trigger sont passés.
      if (user?.accessToken) {
        token.accessToken = user.accessToken;
        token.expiresAt = user.expiresAt;
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken;
      session.refreshToken = token.refreshToken;
      session.expiresAt = token.expiresAt;
      return session;
    },
  },
  pages: {
    signIn: '/login',
  },
});

export const isLocalAdminEnabled = localAdminEnabled;
export const isKeycloakEnabled = Boolean(process.env.KEYCLOAK_ISSUER_URL);
