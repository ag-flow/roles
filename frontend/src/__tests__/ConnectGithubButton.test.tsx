import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import type { ReactNode } from 'react';
import { ConnectGithubButton } from '@/app/my-stack/publication/ConnectGithubButton';
import * as gh from '@/lib/api/github';
import type { GithubIntegrationItem } from '@/lib/types';

function FreshSWR({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      {children}
    </SWRConfig>
  );
}

function makeIntegration(
  overrides: Partial<GithubIntegrationItem> = {},
): GithubIntegrationItem {
  return {
    id: 'i1',
    github_login: 'alice',
    github_user_id: 1,
    scope: 'public_repo',
    last_validated_at: null,
    created_at: '2026-04-01T10:00:00Z',
    ...overrides,
  };
}

describe('ConnectGithubButton (Phase 2 D — multi-comptes)', () => {
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

  it('aucune intégration : affiche le bouton "Connecter GitHub"', async () => {
    vi.spyOn(gh, 'listIntegrations').mockResolvedValue([]);
    render(
      <FreshSWR>
        <ConnectGithubButton />
      </FreshSWR>,
    );
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /connecter github/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/Aucun compte GitHub connecté/i)).toBeInTheDocument();
  });

  it('1 intégration : affiche login + bouton Déconnecter + "Ajouter un compte"', async () => {
    vi.spyOn(gh, 'listIntegrations').mockResolvedValue([makeIntegration()]);
    render(
      <FreshSWR>
        <ConnectGithubButton />
      </FreshSWR>,
    );
    await waitFor(() => {
      expect(screen.getByText('@alice')).toBeInTheDocument();
    });
    expect(
      screen.getByRole('button', { name: /déconnecter/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /ajouter un compte/i }),
    ).toBeInTheDocument();
  });

  it('plusieurs intégrations : affiche tous les logins', async () => {
    vi.spyOn(gh, 'listIntegrations').mockResolvedValue([
      makeIntegration({ id: 'i1', github_login: 'alice' }),
      makeIntegration({ id: 'i2', github_login: 'alice-org', github_user_id: 2 }),
    ]);
    render(
      <FreshSWR>
        <ConnectGithubButton />
      </FreshSWR>,
    );
    await waitFor(() => {
      expect(screen.getByText('@alice')).toBeInTheDocument();
      expect(screen.getByText('@alice-org')).toBeInTheDocument();
    });
  });

  it('clic "Ajouter un compte" appelle startOAuth et redirige', async () => {
    vi.spyOn(gh, 'listIntegrations').mockResolvedValue([makeIntegration()]);
    const startSpy = vi.spyOn(gh, 'startOAuth').mockResolvedValue({
      redirect_url: 'https://github.com/login/oauth/authorize?...',
    });
    const assignSpy = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, assign: assignSpy },
    });

    render(
      <FreshSWR>
        <ConnectGithubButton />
      </FreshSWR>,
    );
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /ajouter un compte/i }),
      ).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByRole('button', { name: /ajouter un compte/i }),
    );
    await waitFor(() => expect(startSpy).toHaveBeenCalled());
    await waitFor(() =>
      expect(assignSpy).toHaveBeenCalledWith(
        'https://github.com/login/oauth/authorize?...',
      ),
    );
  });

  it('clic "Déconnecter" appelle deleteIntegration sur l\'item', async () => {
    vi.spyOn(gh, 'listIntegrations').mockResolvedValue([
      makeIntegration({ id: 'i-target' }),
    ]);
    const delSpy = vi.spyOn(gh, 'deleteIntegration').mockResolvedValue();
    render(
      <FreshSWR>
        <ConnectGithubButton />
      </FreshSWR>,
    );
    await waitFor(() =>
      expect(screen.getByText('@alice')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /déconnecter/i }));
    await waitFor(() => expect(delSpy).toHaveBeenCalledWith('i-target'));
  });
});
