import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VersionList } from '@/app/projects/[id]/role/VersionList';
import type { RoleDocument } from '@/lib/types';

const versions: RoleDocument[] = [
  {
    id: 'v3',
    role_project_id: 'p1',
    section: 'Role',
    name: 'principe',
    content: 'v3',
    version: 3,
    is_current: true,
    locked: false,
    source_run_id: null,
    created_at: '2026-04-29T12:00:00Z',
    updated_at: '2026-04-29T12:00:00Z',
  },
  {
    id: 'v2',
    role_project_id: 'p1',
    section: 'Role',
    name: 'principe',
    content: 'v2',
    version: 2,
    is_current: false,
    locked: false,
    source_run_id: null,
    created_at: '2026-04-28T12:00:00Z',
    updated_at: '2026-04-28T12:00:00Z',
  },
  {
    id: 'v1',
    role_project_id: 'p1',
    section: 'Role',
    name: 'principe',
    content: 'v1',
    version: 1,
    is_current: false,
    locked: false,
    source_run_id: null,
    created_at: '2026-04-27T12:00:00Z',
    updated_at: '2026-04-27T12:00:00Z',
  },
];

describe('VersionList', () => {
  it('liste toutes les versions avec un badge "current" sur celle active', () => {
    render(
      <VersionList
        versions={versions}
        onPromote={vi.fn()}
        onShowDiff={vi.fn()}
      />,
    );
    expect(screen.getByText('v3')).toBeInTheDocument();
    expect(screen.getByText('v2')).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();
    expect(screen.getByText(/current/i)).toBeInTheDocument();
  });

  it('propose Promouvoir et Comparer sur les versions non-current', () => {
    render(
      <VersionList
        versions={versions}
        onPromote={vi.fn()}
        onShowDiff={vi.fn()}
      />,
    );
    // 2 versions non-current → 2 boutons "Promouvoir" + 2 "Comparer"
    expect(
      screen.getAllByRole('button', { name: /promouvoir/i }),
    ).toHaveLength(2);
    expect(
      screen.getAllByRole('button', { name: /comparer/i }),
    ).toHaveLength(2);
  });

  it('clic sur Promouvoir appelle onPromote avec l\'id de la version', () => {
    const onPromote = vi.fn();
    render(
      <VersionList
        versions={versions}
        onPromote={onPromote}
        onShowDiff={vi.fn()}
      />,
    );
    const buttons = screen.getAllByRole('button', { name: /promouvoir/i });
    fireEvent.click(buttons[0]!);
    // La première version non-current = v2
    expect(onPromote).toHaveBeenCalledWith('v2');
  });

  it('clic sur Comparer appelle onShowDiff avec l\'id', () => {
    const onShowDiff = vi.fn();
    render(
      <VersionList
        versions={versions}
        onPromote={vi.fn()}
        onShowDiff={onShowDiff}
      />,
    );
    const buttons = screen.getAllByRole('button', { name: /comparer/i });
    fireEvent.click(buttons[1]!);
    // 2e bouton Comparer = v1 (ordre décroissant → v3 (skipped current), v2, v1)
    expect(onShowDiff).toHaveBeenCalledWith('v1');
  });

  it('omet "Comparer" si onShowDiff est non fourni', () => {
    render(<VersionList versions={versions} onPromote={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /comparer/i })).toBeNull();
  });
});
