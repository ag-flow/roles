import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PushProgressDialog } from '@/app/projects/[id]/role/PushProgressDialog';

describe('PushProgressDialog', () => {
  it('liste les 4 étapes avec puce ✓ pour celles atteintes, ◯ pour les autres', () => {
    render(
      <PushProgressDialog
        steps={['zip_built', 'role_ready']}
        finalStatus={null}
        errorDetail={null}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/Construction du ZIP/i)).toBeInTheDocument();
    expect(screen.getByText(/Création du rôle ag\.flow/i)).toBeInTheDocument();
    expect(screen.getByText(/Upload du ZIP/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Génération du prompt orchestrateur/i),
    ).toBeInTheDocument();
    // Au moins une coche atteinte (zip_built) et un cercle pour zip_uploaded
    const items = screen.getAllByRole('listitem');
    const reached = items.filter((i) => i.textContent?.includes('✓'));
    const pending = items.filter((i) => i.textContent?.includes('◯'));
    expect(reached.length).toBe(2);
    expect(pending.length).toBe(2);
  });

  it('titre "Push terminé" + bouton Fermer quand finalStatus=done', () => {
    render(
      <PushProgressDialog
        steps={['zip_built', 'role_ready', 'zip_uploaded', 'done']}
        finalStatus="done"
        errorDetail={null}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/Push terminé/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /fermer/i })).toBeInTheDocument();
  });

  it('titre "Push échoué" + détail d\'erreur quand finalStatus=failed', () => {
    render(
      <PushProgressDialog
        steps={['zip_built', 'role_ready', 'failed']}
        finalStatus="failed"
        errorDetail="ag.flow returned HTTP 502"
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/Push échoué/i)).toBeInTheDocument();
    expect(
      screen.getByText('ag.flow returned HTTP 502'),
    ).toBeInTheDocument();
  });

  it('Pas de bouton Fermer tant que finalStatus est null (push en cours)', () => {
    render(
      <PushProgressDialog
        steps={['zip_built']}
        finalStatus={null}
        errorDetail={null}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: /fermer/i })).toBeNull();
  });
});
