'use client';

import useSWR from 'swr';
import { getStatus } from '@/lib/api/github';
import { ConnectGithubButton } from './ConnectGithubButton';

export default function PublicationPage() {
  const { data, isLoading, error, mutate } = useSWR(
    'github-status',
    getStatus,
  );

  if (isLoading) return <p style={{ color: '#6b7280' }}>Chargement…</p>;
  if (error || !data) {
    return (
      <p style={{ color: '#dc2626' }}>
        Erreur de chargement du statut GitHub.
      </p>
    );
  }

  return (
    <section>
      <h2 style={{ fontSize: '1.125rem', fontWeight: 600, margin: '0 0 0.5rem' }}>
        Publication GitHub
      </h2>
      <p style={{ color: '#6b7280', fontSize: '0.875rem', margin: '0 0 1rem' }}>
        Connectez votre compte GitHub pour publier vos rôles construits sur un
        de vos repos. Le contenu source (transcriptions, audios, prompts) n&apos;est
        jamais publié.
      </p>
      <div>
        <ConnectGithubButton status={data} onChange={() => mutate()} />
      </div>
    </section>
  );
}
