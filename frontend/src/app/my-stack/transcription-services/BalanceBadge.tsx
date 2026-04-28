'use client';

interface Props {
  balance: number | null;
  cap: number | null;
}

export function BalanceBadge({ balance, cap }: Props) {
  if (balance === null) return null;
  const reference = cap !== null && cap > 0 ? cap : 100;
  const pct = (balance / reference) * 100;
  let color = '#16a34a'; // green
  if (pct < 10) color = '#dc2626'; // red
  else if (pct < 50) color = '#d97706'; // orange
  return (
    <span style={{ color, fontWeight: 500 }}>
      ${balance.toFixed(2)} restants
    </span>
  );
}
