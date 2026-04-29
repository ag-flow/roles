'use client';

interface Props {
  currentContent: string;
  currentVersion: number;
  otherDocId: string;
  onClose: () => void;
}

/**
 * Stub D2.2 — implémentation complète (react-diff-viewer-continued
 * side-by-side) en D2.5.
 */
export function VersionDiff({ otherDocId, onClose }: Props) {
  return (
    <div
      role="dialog"
      style={{
        marginTop: '1rem',
        padding: '1rem',
        background: '#fefce8',
        border: '1px solid #fde047',
        borderRadius: 6,
      }}
    >
      <p style={{ margin: 0 }}>
        Diff vs version {otherDocId} (à implémenter en D2.5)
      </p>
      <button
        type="button"
        onClick={onClose}
        style={{ marginTop: '0.5rem' }}
      >
        Fermer
      </button>
    </div>
  );
}
