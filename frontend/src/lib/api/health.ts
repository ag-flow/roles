export interface HealthPayload {
  status: 'ok' | 'unreachable';
  db: boolean;
}

export async function fetchHealth(apiUrl: string): Promise<HealthPayload> {
  try {
    const resp = await fetch(`${apiUrl}/health/`, { cache: 'no-store' });
    if (!resp.ok) {
      return { status: 'unreachable', db: false };
    }
    const body = await resp.json();
    return { status: body.status === 'ok' ? 'ok' : 'unreachable', db: Boolean(body.db) };
  } catch {
    return { status: 'unreachable', db: false };
  }
}
