'use client';

import { useParams } from 'next/navigation';
import useSWR from 'swr';
import { previewZip } from '@/lib/api/agflow-export';
import { getPublicationConfig } from '@/lib/api/github';
import { listRoleDocumentsGrouped } from '@/lib/api/role-documents';
import { PublicationHistory } from './PublicationHistory';
import { PushToAgflowButton } from './PushToAgflowButton';
import { PublishToGithubButton } from './PublishToGithubButton';
import { RoleDocumentEditor } from './RoleDocumentEditor';

export default function RolePage() {
  const params = useParams();
  const projectId = params['id'] as string;

  const preview = useSWR(['preview-zip', projectId], () => previewZip(projectId));
  const docs = useSWR(['role-documents', projectId], () =>
    listRoleDocumentsGrouped(projectId),
  );
  const publicationCfg = useSWR(['publication-config', projectId], () =>
    getPublicationConfig(projectId),
  );

  if (preview.isLoading || docs.isLoading) {
    return <p style={{ color: '#6b7280' }}>Chargement…</p>;
  }
  if (preview.error || docs.error) {
    return (
      <p style={{ color: '#dc2626' }}>
        Erreur de chargement de la page Rôle.
      </p>
    );
  }

  const previewData = preview.data!;
  const docsData = docs.data!;

  return (
    <div>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>
            {previewData.display_name}
          </h1>
          {previewData.target_role_id && (
            <p style={{ color: '#6b7280', fontSize: '0.875rem', margin: '0.25rem 0 0' }}>
              Déjà poussé sur ag.flow ({previewData.target_role_id})
            </p>
          )}
        </div>
        <PushToAgflowButton
          projectId={projectId}
          preview={previewData}
          onPushed={() => {
            preview.mutate();
            docs.mutate();
          }}
        />
      </header>

      <RoleDocumentEditor
        projectId={projectId}
        sections={docsData.sections}
        onChange={() => {
          docs.mutate();
        }}
      />

      <section
        style={{
          marginTop: '2rem',
          borderTop: '1px solid #e5e7eb',
          paddingTop: '1rem',
        }}
      >
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
          Publication GitHub
        </h2>
        <PublishToGithubButton projectId={projectId} />
        <details style={{ marginTop: '0.75rem' }}>
          <summary
            style={{ cursor: 'pointer', fontSize: '0.85rem', color: '#6b7280' }}
          >
            Historique des publications
          </summary>
          <div style={{ marginTop: '0.5rem' }}>
            <PublicationHistory
              projectId={projectId}
              repoFullName={publicationCfg.data?.repo_full_name ?? null}
            />
          </div>
        </details>
      </section>
    </div>
  );
}
