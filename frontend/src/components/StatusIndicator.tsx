export type StatusKind =
  | 'active'
  | 'configured'
  | 'low'
  | 'expired'
  | 'not-configured'
  | 'invalid'
  | 'revoked'
  | 'exhausted';

interface Props {
  status: StatusKind;
  size?: 'sm' | 'md';
}

const COLORS: Record<StatusKind, string> = {
  active: '#22c55e',
  configured: '#22c55e',
  low: '#f97316',
  expired: '#f97316',
  'not-configured': '#f97316',
  invalid: '#ef4444',
  revoked: '#ef4444',
  exhausted: '#ef4444',
};

const LABELS: Record<StatusKind, string> = {
  active: 'Actif',
  configured: 'Configuré',
  low: 'Crédit bas',
  expired: 'Expiré',
  'not-configured': 'Non configuré',
  invalid: 'Invalide',
  revoked: 'Révoqué',
  exhausted: 'Épuisé',
};

export function StatusIndicator({ status, size = 'md' }: Props) {
  const dotSize = size === 'sm' ? 8 : 12;
  const fontSize = size === 'sm' ? '0.75rem' : '0.875rem';

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize,
      }}
    >
      <span
        aria-hidden
        style={{
          display: 'inline-block',
          width: dotSize,
          height: dotSize,
          borderRadius: '50%',
          backgroundColor: COLORS[status],
          flexShrink: 0,
        }}
      />
      <span>{LABELS[status]}</span>
    </span>
  );
}
