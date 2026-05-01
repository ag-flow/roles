import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RunCard } from '@/app/projects/[id]/analyses/RunCard';
import type { Run } from '@/lib/types';

function makeRun(overrides: Partial<Run> = {}): Run {
  return {
    id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
    role_project_id: 'proj',
    prompt_version_id: 'pv',
    status: 'done',
    output: 'output content',
    llm_provider: 'mistral',
    llm_model: 'mistral-large',
    tokens_input: 100,
    tokens_output: 50,
    cost_usd: 0.0021,
    instruction_override: null,
    started_at: '2026-04-30T10:00:00Z',
    completed_at: '2026-04-30T10:01:00Z',
    error: null,
    created_at: '2026-04-30T10:00:00Z',
    ...overrides,
  };
}

describe('RunCard — badge obsolète (Phase 2 sous-projet C)', () => {
  it('affiche le badge "obsolète" quand run.is_obsolete est true', () => {
    render(<RunCard run={makeRun({ is_obsolete: true })} />);
    expect(screen.getByText('obsolète')).toBeInTheDocument();
  });

  it('n\'affiche pas le badge quand run.is_obsolete est false', () => {
    render(<RunCard run={makeRun({ is_obsolete: false })} />);
    expect(screen.queryByText('obsolète')).toBeNull();
  });

  it('n\'affiche pas le badge quand is_obsolete est undefined (rétro-compat)', () => {
    render(<RunCard run={makeRun()} />);
    expect(screen.queryByText('obsolète')).toBeNull();
  });
});
