'use client';

import { ConnectGithubButton } from './ConnectGithubButton';

export default function PublicationPage() {
  return (
    <section>
      <h2 style={{ fontSize: '1.125rem', fontWeight: 600, margin: '0 0 0.5rem' }}>
        Publication GitHub
      </h2>
      <p style={{ color: '#6b7280', fontSize: '0.875rem', margin: '0 0 1rem' }}>
        Connectez un ou plusieurs comptes GitHub pour publier vos rôles
        construits sur leurs repos. Le contenu source (transcriptions,
        audios, prompts) n&apos;est jamais publié. Vous choisissez le
        compte au moment de chaque publication.
      </p>
      <ConnectGithubButton />
    </section>
  );
}
