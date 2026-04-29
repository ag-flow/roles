import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ConnectGithubButton } from '@/app/my-stack/publication/ConnectGithubButton';
import * as gh from '@/lib/api/github';

describe('ConnectGithubButton', () => {
  let originalLocation: Location;

  beforeEach(() => {
    vi.restoreAllMocks();
    originalLocation = window.location;
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });

  it('non connecté : affiche bouton "Connecter GitHub"', () => {
    render(
      <ConnectGithubButton
        status={{
          connected: false,
          github_login: null,
          scope: null,
          last_validated_at: null,
        }}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByRole('button', { name: /connecter github/i }),
    ).toBeInTheDocument();
  });

  it('connecté : affiche login + bouton Déconnecter', () => {
    render(
      <ConnectGithubButton
        status={{
          connected: true,
          github_login: 'alice',
          scope: 'public_repo',
          last_validated_at: null,
        }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/@alice/)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /déconnecter/i }),
    ).toBeInTheDocument();
  });

  it('clic Connecter appelle startOAuth et redirige', async () => {
    const startSpy = vi.spyOn(gh, 'startOAuth').mockResolvedValue({
      redirect_url: 'https://github.com/login/oauth/authorize?...',
    });
    const assignSpy = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, assign: assignSpy },
    });

    render(
      <ConnectGithubButton
        status={{
          connected: false,
          github_login: null,
          scope: null,
          last_validated_at: null,
        }}
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /connecter github/i }));
    await waitFor(() => expect(startSpy).toHaveBeenCalled());
    await waitFor(() =>
      expect(assignSpy).toHaveBeenCalledWith(
        'https://github.com/login/oauth/authorize?...',
      ),
    );
  });

  it('clic Déconnecter appelle disconnect et onChange', async () => {
    const discSpy = vi
      .spyOn(gh, 'disconnect')
      .mockResolvedValue({ status: 'disconnected' });
    const onChange = vi.fn();
    render(
      <ConnectGithubButton
        status={{
          connected: true,
          github_login: 'alice',
          scope: 'public_repo',
          last_validated_at: null,
        }}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /déconnecter/i }));
    await waitFor(() => expect(discSpy).toHaveBeenCalled());
    await waitFor(() => expect(onChange).toHaveBeenCalled());
  });

  it('affiche une erreur inline si startOAuth échoue', async () => {
    vi.spyOn(gh, 'startOAuth').mockRejectedValue(new Error('500 Server'));
    render(
      <ConnectGithubButton
        status={{
          connected: false,
          github_login: null,
          scope: null,
          last_validated_at: null,
        }}
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /connecter github/i }));
    await waitFor(() => {
      expect(screen.getByText(/500 Server/)).toBeInTheDocument();
    });
  });
});
