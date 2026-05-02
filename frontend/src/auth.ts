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
}

declare module '@auth/core/jwt' {
  interface JWT {
    accessToken?: string;
    refreshToken?: string;
    expiresAt?: number;
  }
}

/**
 * Mode "local login" pour tester sans Keycloak. Activé via
 * `DEV_LOGIN_ENABLED=true` côté frontend + `DISABLE_AUTH=true` côté backend
 * (le backend ne valide alors plus le JWT et utilise un user fixe).
 *
 * Les credentials sont lus depuis l'env :
 *   DEV_LOGIN_USER     (défaut: admin)
 *   DEV_LOGIN_PASSWORD (requis pour activer le provider)
 *
 * Si DEV_LOGIN_PASSWORD est vide, le provider Credentials est désactivé.
 */
const devLoginEnabled =
  process.env.DEV_LOGIN_ENABLED === 'true' &&
  !!process.env.DEV_LOGIN_PASSWORD;

const devUser = process.env.DEV_LOGIN_USER ?? 'admin';
const devPassword = process.env.DEV_LOGIN_PASSWORD ?? '';

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

if (devLoginEnabled) {
  providers.push(
    Credentials({
      id: 'dev-login',
      name: 'Local (dev)',
      credentials: {
        username: { label: 'Identifiant', type: 'text' },
        password: { label: 'Mot de passe', type: 'password' },
      },
      authorize: async (credentials) => {
        const u = String(credentials?.username ?? '');
        const p = String(credentials?.password ?? '');
        if (u === devUser && p === devPassword) {
          return {
            id: 'dev-user',
            name: u,
            email: `${u}@local`,
          };
        }
        return null;
      },
    }),
  );
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers,
  trustHost: true,
  session: { strategy: 'jwt' },
  callbacks: {
    async jwt({ token, account }) {
      if (account?.access_token) {
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
        token.expiresAt = account.expires_at;
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

export const isDevLoginEnabled = devLoginEnabled;
export const isKeycloakEnabled = Boolean(process.env.KEYCLOAK_ISSUER_URL);
