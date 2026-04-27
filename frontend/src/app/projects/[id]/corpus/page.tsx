import { CorpusSearchClient } from './CorpusSearchClient';

export default function CorpusPage({ params }: { params: { id: string } }) {
  return (
    <main style={{ padding: '2rem', maxWidth: 960, margin: '0 auto' }}>
      <h1>Corpus</h1>
      <p style={{ color: '#666', marginBottom: '2rem' }}>
        Recherche sémantique dans le corpus indexé.
      </p>
      <CorpusSearchClient projectId={params.id} />
    </main>
  );
}
