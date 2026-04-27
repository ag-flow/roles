import { auth, signOut } from '@/auth';
import { fetchHealth } from '@/lib/api/health';

export default async function HomePage() {
  const session = await auth();
  // Server Component : préférer l'URL interne au compose (backend:8000) pour le SSR.
  // Côté client, on utiliserait NEXT_PUBLIC_API_URL — sans objet ici puisque ce composant
  // ne s'exécute jamais dans le navigateur.
  const apiUrl =
    process.env.BACKEND_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    'http://localhost:8000';
  const health = await fetchHealth(apiUrl);

  const color = health.status === 'ok' ? '#1f883d' : '#cf222e';

  return (
    <main style={{ padding: '2rem', maxWidth: 720 }}>
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '2rem',
        }}
      >
        <h1>Role Builder</h1>
        {session?.user && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <span style={{ color: '#444' }}>
              {session.user.name ?? session.user.email}
            </span>
            <form
              action={async () => {
                'use server';
                await signOut({ redirectTo: '/login' });
              }}
            >
              <button
                type="submit"
                style={{ padding: '0.4rem 0.8rem', cursor: 'pointer' }}
              >
                Déconnexion
              </button>
            </form>
          </div>
        )}
      </header>
      <p>
        Backend status :{' '}
        <span style={{ color, fontWeight: 600 }}>{health.status}</span>
        {' · '}
        DB :{' '}
        <span style={{ color, fontWeight: 600 }}>
          {health.db ? 'connectée' : 'indisponible'}
        </span>
      </p>
    </main>
  );
}
