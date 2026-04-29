'use client';

import { useState } from 'react';
import { ApiError } from '@/lib/api/client';
import { pushToAgflow } from '@/lib/api/agflow-export';
import type {
  PushPreview,
  PushToAgflowResponse,
} from '@/lib/types';
import { PushPreview as PushPreviewView } from './PushPreview';
import { PushProgressDialog, usePushProgress } from './PushProgressDialog';
import { PostPushBanner } from './PostPushBanner';

interface Props {
  projectId: string;
  preview: PushPreview;
  onPushed: () => void;
}

type Step =
  | { kind: 'idle' }
  | { kind: 'confirm' }
  | { kind: 'pushing' }
  | { kind: 'done'; result: PushToAgflowResponse; partialFailure: 'prompt' | null }
  | { kind: 'error'; message: string; conflict: boolean };

export function PushToAgflowButton({ projectId, preview, onPushed }: Props) {
  const [step, setStep] = useState<Step>({ kind: 'idle' });
  const [generatePrompts, setGeneratePrompts] = useState(false);
  const progress = usePushProgress(projectId, step.kind === 'pushing');

  const isUpdate = !!preview.target_role_id;
  const label = isUpdate ? 'Mettre à jour ag.flow' : 'Pousser vers ag.flow';

  async function confirm() {
    setStep({ kind: 'pushing' });
    try {
      const result = await pushToAgflow(projectId, {
        generate_prompts: generatePrompts,
      });
      const partialFailure: 'prompt' | null =
        generatePrompts && !result.prompt_generated ? 'prompt' : null;
      setStep({ kind: 'done', result, partialFailure });
      onPushed();
    } catch (err) {
      const conflict = err instanceof ApiError && err.status === 409;
      const message =
        err instanceof Error ? err.message : 'Erreur inconnue';
      setStep({ kind: 'error', message, conflict });
    }
  }

  return (
    <>
      <button
        type="button"
        disabled={!preview.ready_to_push}
        onClick={() => setStep({ kind: 'confirm' })}
        style={{
          padding: '0.5rem 1rem',
          background: preview.ready_to_push ? '#2563eb' : '#9ca3af',
          color: 'white',
          border: 0,
          borderRadius: 4,
          cursor: preview.ready_to_push ? 'pointer' : 'not-allowed',
          fontSize: '0.875rem',
          fontWeight: 600,
        }}
      >
        {label}
      </button>

      {step.kind === 'confirm' && (
        <ConfirmDialog
          preview={preview}
          generatePrompts={generatePrompts}
          onTogglePrompts={setGeneratePrompts}
          onCancel={() => setStep({ kind: 'idle' })}
          onConfirm={confirm}
        />
      )}

      {step.kind === 'pushing' && (
        <PushProgressDialog
          steps={progress.steps}
          finalStatus={progress.finalStatus}
          errorDetail={progress.errorDetail}
          onClose={() => setStep({ kind: 'idle' })}
        />
      )}

      {step.kind === 'done' && (
        <PostPushBanner
          projectId={projectId}
          result={step.result}
          partialFailure={step.partialFailure}
          onDismiss={() => setStep({ kind: 'idle' })}
        />
      )}

      {step.kind === 'error' && (
        <ErrorDialog
          message={step.message}
          conflict={step.conflict}
          displayName={preview.display_name}
          onClose={() => setStep({ kind: 'idle' })}
        />
      )}
    </>
  );
}

// --- Sous-composants modaux internes -----------------------------------------

interface ConfirmProps {
  preview: PushPreview;
  generatePrompts: boolean;
  onTogglePrompts: (v: boolean) => void;
  onCancel: () => void;
  onConfirm: () => void;
}

function ConfirmDialog({
  preview,
  generatePrompts,
  onTogglePrompts,
  onCancel,
  onConfirm,
}: ConfirmProps) {
  return (
    <div
      role="dialog"
      aria-label="Confirmer le push"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
      }}
    >
      <div
        style={{
          background: 'white',
          padding: '1.5rem 2rem',
          borderRadius: 8,
          minWidth: 480,
          maxWidth: 720,
        }}
      >
        <PushPreviewView preview={preview} />
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            margin: '1rem 0',
            fontSize: '0.875rem',
          }}
        >
          <input
            type="checkbox"
            checked={generatePrompts}
            onChange={(e) => onTogglePrompts(e.target.checked)}
          />
          Générer le prompt orchestrateur après l&apos;import
        </label>
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: '0.4rem 0.9rem',
              border: '1px solid #d1d5db',
              borderRadius: 4,
              background: 'white',
              cursor: 'pointer',
            }}
          >
            Annuler
          </button>
          <button
            type="button"
            onClick={onConfirm}
            style={{
              padding: '0.4rem 0.9rem',
              background: '#2563eb',
              color: 'white',
              border: 0,
              borderRadius: 4,
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Confirmer
          </button>
        </div>
      </div>
    </div>
  );
}

interface ErrorProps {
  message: string;
  conflict: boolean;
  displayName: string;
  onClose: () => void;
}

function ErrorDialog({ message, conflict, displayName, onClose }: ErrorProps) {
  return (
    <div
      role="dialog"
      aria-label="Échec du push"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
      }}
    >
      <div
        style={{
          background: 'white',
          padding: '1.5rem 2rem',
          borderRadius: 8,
          minWidth: 420,
          maxWidth: 560,
          borderLeft: '4px solid #dc2626',
        }}
      >
        <h3 style={{ margin: '0 0 0.75rem', color: '#991b1b' }}>
          Échec du push
        </h3>
        {conflict ? (
          <p style={{ margin: 0, color: '#374151' }}>
            Le nom <strong>{displayName}</strong> existe déjà sur ag.flow.
            Renommez votre projet (paramètres) avant de pousser.
          </p>
        ) : (
          <pre
            style={{
              margin: 0,
              padding: '0.5rem',
              background: '#fef2f2',
              fontSize: '0.75rem',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {message}
          </pre>
        )}
        <div style={{ marginTop: '1rem', textAlign: 'right' }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '0.4rem 0.9rem',
              border: '1px solid #d1d5db',
              borderRadius: 4,
              background: 'white',
              cursor: 'pointer',
            }}
          >
            Fermer
          </button>
        </div>
      </div>
    </div>
  );
}
