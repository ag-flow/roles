import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { SWRConfig } from 'swr';
import type { ReactNode } from 'react';
import { VersionDiff } from '@/app/projects/[id]/role/VersionDiff';
import * as api from '@/lib/api/role-documents';
import type { RoleDocument } from '@/lib/types';

// Mock léger du viewer (lourd à charger en jsdom). On vérifie juste qu'il
// reçoit les bons oldValue / newValue.
vi.mock('react-diff-viewer-continued', () => ({
  default: ({ oldValue, newValue }: { oldValue: string; newValue: string }) => (
    <div data-testid="diff-viewer">
      <span data-testid="old">{oldValue}</span>
      <span data-testid="new">{newValue}</span>
    </div>
  ),
}));

/** Wrapper SWR avec cache isolé par test (sinon SWR mémorise entre tests). */
function FreshSWR({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      {children}
    </SWRConfig>
  );
}

const otherDoc: RoleDocument = {
  id: 'v2',
  role_project_id: 'p1',
  section: 'Role',
  name: 'principe',
  content: 'contenu de la version 2',
  source_run_id: null,
  version: 2,
  is_current: false,
  locked: false,
  created_at: '2026-04-28T10:00:00Z',
  updated_at: '2026-04-28T10:00:00Z',
};

describe('VersionDiff', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('charge l\'autre version et passe oldValue/newValue au viewer', async () => {
    vi.spyOn(api, 'getRoleDocument').mockResolvedValue(otherDoc);

    render(
      <FreshSWR>
        <VersionDiff
          currentContent="contenu actuel v3"
          currentVersion={3}
          otherDocId="v2"
          onClose={vi.fn()}
        />
      </FreshSWR>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('diff-viewer')).toBeInTheDocument();
    });
    expect(screen.getByTestId('old')).toHaveTextContent(
      'contenu de la version 2',
    );
    expect(screen.getByTestId('new')).toHaveTextContent('contenu actuel v3');
  });

  it('affiche un Chargement initial puis le viewer', async () => {
    let resolveFn: (v: RoleDocument) => void = () => {};
    vi.spyOn(api, 'getRoleDocument').mockImplementation(
      () =>
        new Promise<RoleDocument>((resolve) => {
          resolveFn = resolve;
        }),
    );

    render(
      <FreshSWR>
        <VersionDiff
          currentContent="actuel"
          currentVersion={3}
          otherDocId="v2"
          onClose={vi.fn()}
        />
      </FreshSWR>,
    );
    expect(screen.getByText(/Chargement/i)).toBeInTheDocument();
    resolveFn(otherDoc);
    await waitFor(() => {
      expect(screen.getByTestId('diff-viewer')).toBeInTheDocument();
    });
  });

  it('clic sur Fermer appelle onClose', async () => {
    vi.spyOn(api, 'getRoleDocument').mockResolvedValue(otherDoc);
    const onClose = vi.fn();

    render(
      <FreshSWR>
        <VersionDiff
          currentContent="actuel"
          currentVersion={3}
          otherDocId="v2"
          onClose={onClose}
        />
      </FreshSWR>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('diff-viewer')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /fermer/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
