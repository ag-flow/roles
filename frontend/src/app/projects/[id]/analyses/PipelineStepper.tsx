'use client';

import { useState } from 'react';
import {
  triggerExtraction,
  triggerClustering,
  triggerDecomposition,
  triggerDocumentWriting,
  triggerFullPipeline,
  triggerIdentitySynthesis,
} from '@/lib/api/synthesis';

interface Props {
  projectId: string;
  onRunStarted?: (runId: string | string[]) => void;
}

type Stage = 'extract' | 'cluster' | 'decompose' | 'write' | 'identity' | 'full';

export function PipelineStepper({ projectId, onRunStarted }: Props) {
  const [loading, setLoading] = useState<Record<Stage, boolean>>({
    extract: false,
    cluster: false,
    decompose: false,
    write: false,
    identity: false,
    full: false,
  });
  const [lastRunIds, setLastRunIds] = useState<Record<string, string>>({});

  function setStageLoading(stage: Stage, value: boolean) {
    setLoading((prev) => ({ ...prev, [stage]: value }));
  }

  async function handleExtract() {
    setStageLoading('extract', true);
    try {
      const { run_id } = await triggerExtraction(projectId);
      setLastRunIds((prev) => ({ ...prev, extract: run_id }));
      alert(`Extraction démarrée — run ${run_id.slice(0, 8)}`);
      onRunStarted?.(run_id);
    } catch (err) {
      alert(`Erreur extraction : ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setStageLoading('extract', false);
    }
  }

  async function handleCluster() {
    setStageLoading('cluster', true);
    try {
      const body = lastRunIds['extract'] ? { signal_run_id: lastRunIds['extract'] } : {};
      const { run_id } = await triggerClustering(projectId, body);
      setLastRunIds((prev) => ({ ...prev, cluster: run_id }));
      alert(`Clustering démarré — run ${run_id.slice(0, 8)}`);
      onRunStarted?.(run_id);
    } catch (err) {
      alert(`Erreur clustering : ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setStageLoading('cluster', false);
    }
  }

  async function handleDecompose() {
    setStageLoading('decompose', true);
    try {
      const body = lastRunIds['cluster'] ? { cluster_run_id: lastRunIds['cluster'] } : {};
      const { run_id } = await triggerDecomposition(projectId, body);
      setLastRunIds((prev) => ({ ...prev, decompose: run_id }));
      alert(`Décomposition démarrée — run ${run_id.slice(0, 8)}`);
      onRunStarted?.(run_id);
    } catch (err) {
      alert(`Erreur décomposition : ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setStageLoading('decompose', false);
    }
  }

  async function handleWrite() {
    const planId = window.prompt(
      'ID du plan de décomposition (DocumentPlan ID) :',
      lastRunIds['decompose'] ?? '',
    );
    if (!planId?.trim()) return;

    setStageLoading('write', true);
    try {
      const { run_ids } = await triggerDocumentWriting(projectId, planId.trim());
      alert(`Écriture démarrée — ${run_ids.length} run(s)`);
      onRunStarted?.(run_ids);
    } catch (err) {
      alert(`Erreur écriture : ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setStageLoading('write', false);
    }
  }

  async function handleIdentity() {
    setStageLoading('identity', true);
    try {
      const { run_id } = await triggerIdentitySynthesis(projectId);
      setLastRunIds((prev) => ({ ...prev, identity: run_id }));
      alert(`Synthèse identité démarrée — run ${run_id.slice(0, 8)}`);
      onRunStarted?.(run_id);
    } catch (err) {
      alert(`Erreur synthèse identité : ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setStageLoading('identity', false);
    }
  }

  async function handleFullPipeline() {
    if (
      !window.confirm(
        'Lancer le pipeline complet (extract → cluster → decompose → write-documents → identity) ? '
        + 'L\'opération est synchrone et peut prendre 2-5 min selon la taille du corpus.',
      )
    ) {
      return;
    }
    setStageLoading('full', true);
    try {
      const result = await triggerFullPipeline(projectId, { include_identity: true });
      const docCount = result.document_run_ids.length;
      const idText = result.identity_run_id
        ? `, identity ${result.identity_run_id.slice(0, 8)}`
        : '';
      alert(
        `Pipeline terminé — extract ${result.extract_run_id.slice(0, 8)}, `
        + `cluster ${result.cluster_run_id.slice(0, 8)}, `
        + `decompose ${result.decompose_run_id.slice(0, 8)}, `
        + `${docCount} doc run(s)${idText}.`,
      );
      // Notifie pour rafraichir la liste des runs
      onRunStarted?.([
        result.extract_run_id,
        result.cluster_run_id,
        result.decompose_run_id,
        ...result.document_run_ids,
        ...(result.identity_run_id ? [result.identity_run_id] : []),
      ]);
    } catch (err) {
      alert(`Erreur pipeline : ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setStageLoading('full', false);
    }
  }

  const buttonStyle: React.CSSProperties = {
    padding: '0.5rem 1rem',
    borderRadius: 6,
    border: '1px solid #d0d0d0',
    background: '#fff',
    cursor: 'pointer',
    fontSize: '0.9rem',
    fontWeight: 500,
  };

  const disabledStyle: React.CSSProperties = {
    ...buttonStyle,
    opacity: 0.5,
    cursor: 'not-allowed',
  };

  const fullButtonStyle: React.CSSProperties = {
    ...buttonStyle,
    background: '#7c3aed',
    color: 'white',
    border: 0,
    fontWeight: 600,
  };

  const anyStageLoading = Object.values(loading).some((v) => v);

  return (
    <div style={{ marginBottom: '1.5rem' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          padding: '0.75rem 1rem',
          background: '#faf5ff',
          borderRadius: 8,
          border: '1px solid #e9d5ff',
          marginBottom: '0.75rem',
        }}
      >
        <button
          onClick={handleFullPipeline}
          disabled={anyStageLoading}
          style={anyStageLoading ? { ...fullButtonStyle, opacity: 0.5, cursor: 'not-allowed' } : fullButtonStyle}
        >
          {loading.full ? 'Pipeline en cours…' : '⚡ Lancer le pipeline complet'}
        </button>
        <span style={{ fontSize: '0.85rem', color: '#6b46c1' }}>
          extract → cluster → decompose → write-documents → identity
        </span>
      </div>

    <div
      style={{
        display: 'flex',
        gap: '0.75rem',
        flexWrap: 'wrap',
        alignItems: 'center',
        padding: '1rem',
        background: '#f9f9f9',
        borderRadius: 8,
        border: '1px solid #eaeaea',
      }}
    >
      <button
        onClick={handleExtract}
        disabled={loading.extract}
        style={loading.extract ? disabledStyle : buttonStyle}
      >
        {loading.extract ? 'En cours…' : 'Extraire signaux'}
      </button>

      <span style={{ color: '#ccc' }}>→</span>

      <button
        onClick={handleCluster}
        disabled={loading.cluster}
        style={loading.cluster ? disabledStyle : buttonStyle}
      >
        {loading.cluster ? 'En cours…' : 'Regrouper en clusters'}
      </button>

      <span style={{ color: '#ccc' }}>→</span>

      <button
        onClick={handleDecompose}
        disabled={loading.decompose}
        style={loading.decompose ? disabledStyle : buttonStyle}
      >
        {loading.decompose ? 'En cours…' : 'Planifier documents'}
      </button>

      <span style={{ color: '#ccc' }}>→</span>

      <button
        onClick={handleWrite}
        disabled={loading.write}
        style={loading.write ? disabledStyle : buttonStyle}
        title="Nécessite un plan de décomposition"
      >
        {loading.write ? 'En cours…' : 'Écrire documents'}
      </button>

      <span style={{ color: '#ccc' }}>→</span>

      <button
        onClick={handleIdentity}
        disabled={loading.identity}
        style={loading.identity ? disabledStyle : buttonStyle}
      >
        {loading.identity ? 'En cours…' : 'Générer identity'}
      </button>
    </div>
    </div>
  );
}
