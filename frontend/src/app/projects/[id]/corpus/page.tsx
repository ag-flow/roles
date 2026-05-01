import { CorpusSearchClient } from './CorpusSearchClient';
import { RebuildCorpusButton } from './RebuildCorpusButton';

export default function CorpusPage({ params }: { params: { id: string } }) {
  return (
    <main style={{ padding: '2rem', maxWidth: 960, margin: '0 auto' }}>
      <h1>Corpus</h1>
      <p style={{ color: '#666', marginBottom: '2rem' }}>
        Recherche sémantique dans le corpus indexé.
      </p>
      <CorpusSearchClient projectId={params.id} />
      <hr style={{ margin: '2rem 0', border: 'none', borderTop: '1px solid #e5e7eb' }} />
      <h2 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>
        Maintenance
      </h2>
      <p style={{ color: '#6b7280', fontSize: '0.85rem', margin: '0.25rem 0' }}>
        Si vous changez la stratégie de chunking ou la dimension d&apos;embeddings,
        reconstruisez le corpus pour ré-indexer les transcripts existants.
      </p>
      <RebuildCorpusButton projectId={params.id} />
    </main>
  );
}
