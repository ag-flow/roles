import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DocumentActions } from '@/app/projects/[id]/role/DocumentActions';
import * as api from '@/lib/api/role-documents';
import type { RoleDocument } from '@/lib/types';

const baseDoc: RoleDocument = {
  id: 'd1',
  role_project_id: 'p1',
  section: 'Role',
  name: 'principe',
  content: 'contenu',
  source_run_id: null,
  version: 1,
  is_current: true,
  locked: false,
  created_at: '2026-04-29T10:00:00Z',
  updated_at: '2026-04-29T10:00:00Z',
};

describe('DocumentActions', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('affiche "Verrouiller" + "Régénérer" sur un doc non verrouillé', () => {
    render(
      <DocumentActions
        doc={baseDoc}
        onLockChange={vi.fn()}
        onRegenerated={vi.fn()}
      />,
    );
    expect(
      screen.getByRole('button', { name: /verrouiller/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /régénérer/i }),
    ).toBeInTheDocument();
  });

  it('affiche "Déverrouiller" sur un doc verrouillé, Régénérer désactivé', () => {
    render(
      <DocumentActions
        doc={{ ...baseDoc, locked: true }}
        onLockChange={vi.fn()}
        onRegenerated={vi.fn()}
      />,
    );
    expect(
      screen.getByRole('button', { name: /déverrouiller/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /régénérer/i })).toBeDisabled();
  });

  it('clic "Verrouiller" appelle lockRoleDocument et onLockChange', async () => {
    const lockSpy = vi
      .spyOn(api, 'lockRoleDocument')
      .mockResolvedValue({ status: 'locked' });
    const onLockChange = vi.fn();

    render(
      <DocumentActions
        doc={baseDoc}
        onLockChange={onLockChange}
        onRegenerated={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /verrouiller/i }));
    await waitFor(() => expect(lockSpy).toHaveBeenCalledWith('d1'));
    await waitFor(() => expect(onLockChange).toHaveBeenCalled());
  });

  it('clic "Déverrouiller" appelle unlockRoleDocument', async () => {
    const unlockSpy = vi
      .spyOn(api, 'unlockRoleDocument')
      .mockResolvedValue({ status: 'unlocked' });

    render(
      <DocumentActions
        doc={{ ...baseDoc, locked: true }}
        onLockChange={vi.fn()}
        onRegenerated={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /déverrouiller/i }));
    await waitFor(() => expect(unlockSpy).toHaveBeenCalledWith('d1'));
  });

  it('clic "Régénérer" appelle regenerateRoleDocument et onRegenerated', async () => {
    const regenSpy = vi
      .spyOn(api, 'regenerateRoleDocument')
      .mockResolvedValue({ run_id: 'r1' });
    const onRegen = vi.fn();

    render(
      <DocumentActions
        doc={baseDoc}
        onLockChange={vi.fn()}
        onRegenerated={onRegen}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /régénérer/i }));
    await waitFor(() => expect(regenSpy).toHaveBeenCalled());
    expect(regenSpy.mock.calls[0]?.[0]).toBe('d1');
    await waitFor(() => expect(onRegen).toHaveBeenCalled());
  });
});
