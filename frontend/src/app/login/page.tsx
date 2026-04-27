import { signIn } from '@/auth';

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
      <p style={{ color: '#666', marginBottom: '2rem' }}>
        Authentification via Keycloak.
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
            borderRadius: '6px',
            cursor: 'pointer',
            width: '100%',
          }}
        >
          Se connecter avec Keycloak
        </button>
      </form>
    </main>
  );
}
