'use client';

import { useParams } from 'next/navigation';
import useSWR from 'swr';
import { previewZip } from '@/lib/api/agflow-export';
import { listRoleDocumentsGrouped } from '@/lib/api/role-documents';
import { PushToAgflowButton } from './PushToAgflowButton';
import { RoleDocumentEditor } from './RoleDocumentEditor';

export default function RolePage() {
  const params = useParams();
  const projectId = params['id'] as string;

  const preview = useSWR(['preview-zip', projectId], () => previewZip(projectId));
  const docs = useSWR(['role-documents', projectId], () =>
    listRoleDocumentsGrouped(projectId),
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
    </div>
  );
}
