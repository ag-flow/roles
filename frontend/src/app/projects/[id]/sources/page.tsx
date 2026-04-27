'use client';

import { useState } from 'react';
import { AddSourceDialog } from './AddSourceDialog';

// Note : la liste des sources d'un projet sera ajoutée quand l'endpoint
// GET /api/role-projects/{id}/sources sera disponible (post Sprint 2).
// Pour le MVP : page de création + redirect vers la page détail.
export default function SourcesPage({ params }: { params: { id: string } }) {
  const [showDialog, setShowDialog] = useState(false);

  return (
    <main style={{ padding: '2rem', maxWidth: 960 }}>
      <h1>Sources du projet</h1>
      <p style={{ color: '#666' }}>
        Ajoute une chaîne YouTube, un compte Instagram ou TikTok pour démarrer la collecte du
        corpus.
      </p>
      <button onClick={() => setShowDialog(true)}>+ Ajouter une source</button>
      {showDialog && (
        <AddSourceDialog roleProjectId={params.id} onClose={() => setShowDialog(false)} />
      )}
    </main>
  );
}
