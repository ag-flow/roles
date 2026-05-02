import Link from 'next/link';
import { auth, signOut } from '@/auth';
import { fetchHealth } from '@/lib/api/health';
import type { RoleProject } from '@/lib/types';

export const dynamic = 'force-dynamic';

const BACKEND_URL =
  process.env.BACKEND_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://localhost:8000';

async function fetchProjects(
  accessToken: string | undefined,
): Promise<RoleProject[]> {
  if (!accessToken) return [];
  try {
    const resp = await fetch(`${BACKEND_URL}/api/role-projects`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: 'no-store',
    });
    if (!resp.ok) return [];
    return (await resp.json()) as RoleProject[];
  } catch {
    return [];
  }
}

export default async function HomePage() {
  const session = await auth();
  const health = await fetchHealth(BACKEND_URL);
  const projects = session ? await fetchProjects(session.accessToken) : [];

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
        <h1 style={{ margin: 0 }}>Role Builder</h1>
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
        Construis des rôles ag.flow à partir de corpus audio scrapés
        (YouTube / Instagram / TikTok).
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

      <nav
        style={{
          display: 'flex',
          gap: '1rem',
          marginBottom: '2rem',
          flexWrap: 'wrap',
        }}
      >
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

      <section>
        <h2 style={{ fontSize: '1.1rem', margin: '0 0 0.75rem' }}>
          Mes projets de rôle
        </h2>
        {projects.length === 0 ? (
          <p style={{ color: '#6b7280', fontSize: '0.9rem' }}>
            Aucun projet pour l&apos;instant. La création se fait actuellement
            via l&apos;API ou en base — l&apos;UI de création arrivera dans
            une prochaine itération.
          </p>
        ) : (
          <ul
            style={{
              listStyle: 'none',
              padding: 0,
              margin: 0,
              display: 'grid',
              gap: '0.5rem',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            }}
          >
            {projects.map((p) => (
              <li
                key={p.id}
                style={{
                  border: '1px solid #e5e7eb',
                  borderRadius: 6,
                  padding: '0.75rem 1rem',
                  background: 'white',
                }}
              >
                <Link
                  href={`/projects/${p.id}/sources`}
                  style={{
                    display: 'block',
                    color: '#111827',
                    textDecoration: 'none',
                  }}
                >
                  <strong style={{ display: 'block', marginBottom: '0.25rem' }}>
                    {p.display_name}
                  </strong>
                  {p.description && (
                    <span
                      style={{
                        display: 'block',
                        color: '#6b7280',
                        fontSize: '0.85rem',
                      }}
                    >
                      {p.description}
                    </span>
                  )}
                  <span
                    style={{
                      display: 'block',
                      marginTop: '0.5rem',
                      fontSize: '0.8rem',
                      color: '#2563eb',
                    }}
                  >
                    Ouvrir →
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
