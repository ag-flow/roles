import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DocumentEditor } from '@/app/projects/[id]/role/DocumentEditor';
import * as api from '@/lib/api/role-documents';
import type { RoleDocument } from '@/lib/types';

const baseDoc: RoleDocument = {
  id: 'd1',
  role_project_id: 'p1',
  section: 'Role',
  name: 'principe',
  content: 'contenu original',
  source_run_id: null,
  version: 1,
  is_current: true,
  locked: false,
  created_at: '2026-04-29T10:00:00Z',
  updated_at: '2026-04-29T10:00:00Z',
};

describe('DocumentEditor', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('affiche le contenu en lecture seule par défaut + bouton Éditer', () => {
    render(<DocumentEditor doc={baseDoc} onSaved={vi.fn()} />);
    expect(screen.getByText('contenu original')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /éditer/i }),
    ).toBeInTheDocument();
    // Pas de textarea visible
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('clic sur Éditer affiche un textarea pré-rempli', () => {
    render(<DocumentEditor doc={baseDoc} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /éditer/i }));
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(textarea.value).toBe('contenu original');
  });

  it('clic sur Enregistrer appelle updateRoleDocumentContent et onSaved', async () => {
    const updateSpy = vi
      .spyOn(api, 'updateRoleDocumentContent')
      .mockResolvedValue({ ...baseDoc, content: 'modifié' });
    const onSaved = vi.fn();

    render(<DocumentEditor doc={baseDoc} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole('button', { name: /éditer/i }));
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'modifié' },
    });
    fireEvent.click(screen.getByRole('button', { name: /enregistrer/i }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith('d1', 'modifié');
    });
    expect(onSaved).toHaveBeenCalled();
  });

  it('Annuler revient en lecture sans appeler updateContent', () => {
    const updateSpy = vi.spyOn(api, 'updateRoleDocumentContent');
    render(<DocumentEditor doc={baseDoc} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /éditer/i }));
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'modifié' },
    });
    fireEvent.click(screen.getByRole('button', { name: /annuler/i }));
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(updateSpy).not.toHaveBeenCalled();
  });

  it('bouton Éditer désactivé si doc.locked', () => {
    render(<DocumentEditor doc={{ ...baseDoc, locked: true }} onSaved={vi.fn()} />);
    expect(screen.getByRole('button', { name: /éditer/i })).toBeDisabled();
  });

  it('Enregistrer désactivé tant que le contenu n\'a pas changé', () => {
    render(<DocumentEditor doc={baseDoc} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /éditer/i }));
    expect(screen.getByRole('button', { name: /enregistrer/i })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'changé' },
    });
    expect(screen.getByRole('button', { name: /enregistrer/i })).toBeEnabled();
  });
});
