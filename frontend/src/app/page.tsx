import { fetchHealth } from '@/lib/api/health';

export default async function HomePage() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  const health = await fetchHealth(apiUrl);

  const color = health.status === 'ok' ? '#1f883d' : '#cf222e';

  return (
    <main style={{ padding: '2rem', maxWidth: 720 }}>
      <h1>Role Builder</h1>
      <p>
        Backend status :{' '}
        <span style={{ color, fontWeight: 600 }}>{health.status}</span>
        {' · '}
        DB : <span style={{ color, fontWeight: 600 }}>{health.db ? 'connectée' : 'indisponible'}</span>
      </p>
    </main>
  );
}
