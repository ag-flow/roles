'use client';

import { useState } from 'react';
import useSWR from 'swr';
import {
  getPublicationConfig,
  getStatus,
  listIntegrations,
  listRepos,
  publishToGithub,
  setPublicationConfig,
} from '@/lib/api/github';
import type { GithubIntegrationItem, PublishResponse } from '@/lib/types';
import { PublishToGithubConfigDialog } from './PublishToGithubDialog';

interface Props {
  projectId: string;
}

type Step =
  | { kind: 'idle' }
  | { kind: 'configure' }
  | { kind: 'publishing' }
  | { kind: 'done'; result: PublishResponse }
  | { kind: 'error'; message: string };

export function PublishToGithubButton({ projectId }: Props) {
  const [step, setStep] = useState<Step>({ kind: 'idle' });
  const [savingConfig, setSavingConfig] = useState(false);
  const [selectedIntegrationId, setSelectedIntegrationId] = useState<string | null>(
    null,
  );

  const status = useSWR('github-status', getStatus);
  const integrations = useSWR<GithubIntegrationItem[]>(
    'github-integrations',
    listIntegrations,
  );
  const config = useSWR(['publication-config', projectId], () =>
    getPublicationConfig(projectId),
  );
  const repos = useSWR(
    ['github-repos', selectedIntegrationId],
    () => listRepos(selectedIntegrationId ?? undefined),
    {
      revalidateIfStale: false,
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    },
  );

  if (!status.data) {
    return null;
  }

  if (!status.data.connected) {
    return (
      <p style={{ color: '#6b7280', fontSize: '0.875rem' }}>
        GitHub non connecté.{' '}
        <a href="/my-stack/publication">Connecter mon compte →</a>
      </p>
    );
  }

  async function publish() {
    setStep({ kind: 'publishing' });
    try {
      const result = await publishToGithub(
        projectId,
        selectedIntegrationId ?? undefined,
      );
      setStep({ kind: 'done', result });
    } catch (err) {
      setStep({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Erreur inconnue',
      });
    }
  }

  async function saveConfig(cfg: {
    repo_full_name: string;
    target_subdirectory: string;
    branch: string;
    commit_message_template: string;
    license_choice: 'none' | 'polyform-nc' | 'cc-by-nc-sa-4.0' | 'cc-by-4.0' | 'mit';
  }) {
    setSavingConfig(true);
    try {
      await setPublicationConfig(projectId, cfg);
      await config.mutate();
      setStep({ kind: 'idle' });
    } finally {
      setSavingConfig(false);
    }
  }

  const isConfigured = !!config.data;
  const buttonLabel = isConfigured ? 'Publier sur GitHub' : 'Configurer la publication';

  const integrationsList = integrations.data ?? [];
  const showIntegrationSelector = integrationsList.length > 1;

  return (
    <div>
      {showIntegrationSelector && (
        <div style={{ marginBottom: '0.5rem', fontSize: '0.85rem' }}>
          <label>
            Compte GitHub :{' '}
            <select
              value={selectedIntegrationId ?? ''}
              onChange={(e) =>
                setSelectedIntegrationId(e.target.value || null)
              }
              style={{ padding: '0.25rem' }}
            >
              <option value="">Compte par défaut (le plus récent)</option>
              {integrationsList.map((it) => (
                <option key={it.id} value={it.id}>
                  @{it.github_login}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
        <button
          type="button"
          onClick={() => {
            if (isConfigured) publish();
            else {
              repos.mutate();
              setStep({ kind: 'configure' });
            }
          }}
          disabled={step.kind === 'publishing'}
          style={{
            padding: '0.5rem 1rem',
            background: '#24292f',
            color: 'white',
            border: 0,
            borderRadius: 4,
            cursor: step.kind === 'publishing' ? 'not-allowed' : 'pointer',
            opacity: step.kind === 'publishing' ? 0.6 : 1,
            fontSize: '0.875rem',
            fontWeight: 600,
          }}
        >
          {step.kind === 'publishing' ? 'Publication…' : buttonLabel}
        </button>
        {isConfigured && (
          <button
            type="button"
            onClick={() => {
              repos.mutate();
              setStep({ kind: 'configure' });
            }}
            style={{
              padding: '0.4rem 0.7rem',
              background: 'white',
              border: '1px solid #d1d5db',
              borderRadius: 4,
              fontSize: '0.8rem',
              cursor: 'pointer',
            }}
          >
            Modifier la config
          </button>
        )}
        {isConfigured && config.data && (
          <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>
            cible : <code>{config.data.repo_full_name}/{config.data.target_subdirectory}</code>
          </span>
        )}
      </div>

      {step.kind === 'configure' && (
        <PublishToGithubConfigDialog
          repos={repos.data ?? []}
          initial={config.data ?? null}
          onCancel={() => setStep({ kind: 'idle' })}
          onSave={saveConfig}
          saving={savingConfig}
        />
      )}

      {step.kind === 'done' && (
        <div
          role="status"
          style={{
            marginTop: '0.75rem',
            padding: '0.75rem 1rem',
            borderLeft: '4px solid #16a34a',
            background: '#f0fdf4',
            color: '#14532d',
            borderRadius: 4,
          }}
        >
          <strong>✓ Rôle publié sur GitHub</strong>
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.85rem' }}>
            {step.result.files_count} fichier(s),{' '}
            {step.result.commit_sha?.slice(0, 7) ?? '?'} ·{' '}
            <a href={step.result.url} target="_blank" rel="noopener noreferrer">
              Voir sur GitHub →
            </a>
          </p>
          {step.result.tag_name && step.result.tag_url && (
            <p style={{ margin: '0.25rem 0 0', fontSize: '0.85rem' }}>
              Tag annoté :{' '}
              <a
                href={step.result.tag_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ fontFamily: 'monospace' }}
              >
                {step.result.tag_name}
              </a>
            </p>
          )}
          <button
            type="button"
            onClick={() => setStep({ kind: 'idle' })}
            style={{
              marginTop: '0.5rem',
              padding: '0.3rem 0.7rem',
              background: 'transparent',
              border: '1px solid #16a34a',
              borderRadius: 4,
              color: '#14532d',
              cursor: 'pointer',
              fontSize: '0.8rem',
            }}
          >
            Fermer
          </button>
        </div>
      )}

      {step.kind === 'error' && (
        <div
          role="status"
          style={{
            marginTop: '0.75rem',
            padding: '0.75rem 1rem',
            borderLeft: '4px solid #dc2626',
            background: '#fef2f2',
            color: '#991b1b',
            borderRadius: 4,
          }}
        >
          <strong>Échec de la publication</strong>
          <pre
            style={{
              margin: '0.25rem 0',
              fontSize: '0.75rem',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {step.message}
          </pre>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              onClick={publish}
              style={{
                padding: '0.3rem 0.7rem',
                background: '#dc2626',
                color: 'white',
                border: 0,
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: '0.8rem',
                fontWeight: 600,
              }}
            >
              Réessayer
            </button>
            <button
              type="button"
              onClick={() => setStep({ kind: 'idle' })}
              style={{
                padding: '0.3rem 0.7rem',
                background: 'white',
                border: '1px solid #fca5a5',
                borderRadius: 4,
                color: '#991b1b',
                cursor: 'pointer',
                fontSize: '0.8rem',
              }}
            >
              Fermer
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
