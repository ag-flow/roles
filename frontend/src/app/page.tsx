import Link from 'next/link';
import { auth, signOut } from '@/auth';
import { fetchHealth } from '@/lib/api/health';

export const dynamic = 'force-dynamic';

const BACKEND_URL =
  process.env.BACKEND_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://localhost:8000';

export default async function HomePage() {
  const session = await auth();
  const health = await fetchHealth(BACKEND_URL);
  const healthColor = health.status === 'ok' ? '#1f883d' : '#cf222e';

  return (
    <main style={{ padding: '2rem', maxWidth: 960, margin: '0 auto' }}>
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '2rem',
        }}
      >
        <h1 style={{ margin: 0 }}>agflow.roles</h1>
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
                style={{
                  padding: '0.4rem 0.8rem',
                  cursor: 'pointer',
                  border: '1px solid #d1d5db',
                  borderRadius: 4,
                  background: 'white',
                }}
              >
                Déconnexion
              </button>
            </form>
          </div>
        )}
      </header>

      <p style={{ color: '#555', marginBottom: '0.5rem' }}>
        Stack d&apos;acquisition de corpus (YouTube / Instagram / TikTok). Le
        pilotage se fait par conversation via la passerelle MCP&nbsp;;
        l&apos;interface web ne sert qu&apos;à gérer ta stack (secrets, clés,
        comptes).
      </p>
      <p style={{ fontSize: '0.85rem', color: '#888', marginBottom: '2rem' }}>
        Backend{' '}
        <span style={{ color: healthColor, fontWeight: 600 }}>
          {health.status}
        </span>
        {' · '}
        DB{' '}
        <span style={{ color: healthColor, fontWeight: 600 }}>
          {health.db ? 'connectée' : 'indisponible'}
        </span>
      </p>

      <nav style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
        <Link
          href="/my-stack"
          style={{
            padding: '0.5rem 1rem',
            background: '#2563eb',
            color: 'white',
            borderRadius: 6,
            textDecoration: 'none',
            fontSize: '0.9rem',
            fontWeight: 600,
          }}
        >
          Ma stack
        </Link>
      </nav>
    </main>
  );
}
