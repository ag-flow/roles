import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PublishToGithubConfigDialog } from '@/app/projects/[id]/role/PublishToGithubDialog';
import type { GithubRepo, PublicationConfig } from '@/lib/types';

const repos: GithubRepo[] = [
  {
    full_name: 'alice/roles',
    private: false,
    default_branch: 'main',
    html_url: 'x',
  },
  {
    full_name: 'alice/private',
    private: true,
    default_branch: 'main',
    html_url: 'y',
  },
];

describe('PublishToGithubConfigDialog', () => {
  it('liste les 5 options de licence', () => {
    render(
      <PublishToGithubConfigDialog
        repos={repos}
        initial={null}
        onCancel={vi.fn()}
        onSave={vi.fn()}
        saving={false}
      />,
    );
    expect(screen.getByLabelText(/Aucune licence/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/PolyForm Noncommercial/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/BY-NC-SA/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^MIT$/i)).toBeInTheDocument();
  });

  it('liste les repos avec un suffixe (privé) sur les privés', () => {
    render(
      <PublishToGithubConfigDialog
        repos={repos}
        initial={null}
        onCancel={vi.fn()}
        onSave={vi.fn()}
        saving={false}
      />,
    );
    expect(screen.getByText(/alice\/roles/)).toBeInTheDocument();
    expect(screen.getByText(/alice\/private \(privé\)/)).toBeInTheDocument();
  });

  it('pré-remplit les champs depuis initial config', () => {
    const initial: PublicationConfig = {
      role_project_id: 'rp-1',
      repo_full_name: 'alice/roles',
      target_subdirectory: 'ux-clea',
      branch: 'main',
      commit_message_template: 'Custom {role_name}',
      license_choice: 'mit',
    };
    render(
      <PublishToGithubConfigDialog
        repos={repos}
        initial={initial}
        onCancel={vi.fn()}
        onSave={vi.fn()}
        saving={false}
      />,
    );
    const subdir = screen.getByDisplayValue('ux-clea');
    expect(subdir).toBeInTheDocument();
    expect(screen.getByDisplayValue('Custom {role_name}')).toBeInTheDocument();
    // Radio MIT cochée
    const mitRadio = screen.getByRole('radio', { name: /MIT/i }) as HTMLInputElement;
    expect(mitRadio.checked).toBe(true);
  });

  it('soumet onSave avec les valeurs du formulaire', () => {
    const onSave = vi.fn();
    render(
      <PublishToGithubConfigDialog
        repos={repos}
        initial={null}
        onCancel={vi.fn()}
        onSave={onSave}
        saving={false}
      />,
    );
    const subdir = screen.getByLabelText(/Sous-répertoire/i);
    fireEvent.change(subdir, { target: { value: 'roles/clea' } });

    fireEvent.click(screen.getByRole('button', { name: /enregistrer/i }));
    expect(onSave).toHaveBeenCalledTimes(1);
    const arg = onSave.mock.calls[0]![0];
    expect(arg.target_subdirectory).toBe('roles/clea');
    expect(arg.repo_full_name).toBe('alice/roles');  // premier repo par défaut
    expect(arg.license_choice).toBe('none');  // défaut radio
  });

  it('Annuler appelle onCancel sans soumettre', () => {
    const onCancel = vi.fn();
    const onSave = vi.fn();
    render(
      <PublishToGithubConfigDialog
        repos={repos}
        initial={null}
        onCancel={onCancel}
        onSave={onSave}
        saving={false}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /annuler/i }));
    expect(onCancel).toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('bouton Enregistrer désactivé si saving=true', () => {
    render(
      <PublishToGithubConfigDialog
        repos={repos}
        initial={null}
        onCancel={vi.fn()}
        onSave={vi.fn()}
        saving={true}
      />,
    );
    expect(
      screen.getByRole('button', { name: /enregistrement/i }),
    ).toBeDisabled();
  });
});
