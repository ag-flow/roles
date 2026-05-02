import { isLocalAdminEnabled, isKeycloakEnabled, signIn } from '@/auth';

// Lit les env vars (LOCAL_ADMIN_*, KEYCLOAK_ISSUER_URL) à chaque requête
// plutôt qu'au build. Sinon le rendu SSG du build CI fige la page sur
// l'état où aucune méthode d'auth n'est configurée.
export const dynamic = 'force-dynamic';

export default function LoginPage() {
  return (
    <main
      style={{
        padding: '2rem',
        maxWidth: 480,
        margin: '4rem auto',
        fontFamily: 'system-ui, sans-serif',
      }}
    >
      <h1>Connexion à Role Builder</h1>

      {isKeycloakEnabled && (
        <section style={{ marginBottom: '2rem' }}>
          <p style={{ color: '#666', marginBottom: '0.75rem' }}>
            Authentification Keycloak (production).
          </p>
          <form
            action={async () => {
              'use server';
              await signIn('keycloak', { redirectTo: '/' });
            }}
          >
            <button
              type="submit"
              style={{
                padding: '0.75rem 1.5rem',
                fontSize: '1rem',
                backgroundColor: '#1f883d',
                color: 'white',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                width: '100%',
              }}
            >
              Se connecter avec Keycloak
            </button>
          </form>
        </section>
      )}

      {isLocalAdminEnabled && (
        <section
          style={{
            marginTop: isKeycloakEnabled ? '2rem' : 0,
            paddingTop: isKeycloakEnabled ? '1rem' : 0,
            borderTop: isKeycloakEnabled ? '1px solid #e5e7eb' : 'none',
          }}
        >
          <p style={{ color: '#666', marginBottom: '0.75rem' }}>
            Connexion administrateur local.
          </p>
          <form
            action={async (formData) => {
              'use server';
              await signIn('local-admin', {
                username: String(formData.get('username') ?? ''),
                password: String(formData.get('password') ?? ''),
                redirectTo: '/',
              });
            }}
          >
            <label
              style={{
                display: 'block',
                marginBottom: '0.75rem',
                fontSize: '0.9rem',
              }}
            >
              <span style={{ display: 'block', marginBottom: '0.25rem' }}>
                Identifiant
              </span>
              <input
                name="username"
                type="text"
                required
                autoComplete="username"
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  border: '1px solid #d1d5db',
                  borderRadius: 4,
                  fontSize: '1rem',
                  boxSizing: 'border-box',
                }}
              />
            </label>
            <label
              style={{
                display: 'block',
                marginBottom: '1rem',
                fontSize: '0.9rem',
              }}
            >
              <span style={{ display: 'block', marginBottom: '0.25rem' }}>
                Mot de passe
              </span>
              <input
                name="password"
                type="password"
                required
                autoComplete="current-password"
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  border: '1px solid #d1d5db',
                  borderRadius: 4,
                  fontSize: '1rem',
                  boxSizing: 'border-box',
                }}
              />
            </label>
            <button
              type="submit"
              style={{
                padding: '0.75rem 1.5rem',
                fontSize: '1rem',
                backgroundColor: '#2563eb',
                color: 'white',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                width: '100%',
              }}
            >
              Se connecter
            </button>
          </form>
        </section>
      )}

      {!isKeycloakEnabled && !isLocalAdminEnabled && (
        <p style={{ color: '#dc2626' }}>
          Aucune méthode d&apos;authentification n&apos;est configurée. Définissez
          KEYCLOAK_ISSUER_URL côté frontend, ou activez l&apos;admin local
          (LOCAL_ADMIN_ENABLED + LOCAL_ADMIN_PASSWORD côté backend).
        </p>
      )}
    </main>
  );
}
