import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import type { ReactNode } from 'react';
import { AppsMenu } from '@/components/AppsMenu';
import * as appsApi from '@/lib/api/apps';

function FreshSWR({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      {children}
    </SWRConfig>
  );
}

describe('AppsMenu', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('reste caché si la liste est vide', async () => {
    vi.spyOn(appsApi, 'getApps').mockResolvedValue({ urls: [] });
    render(
      <FreshSWR>
        <AppsMenu />
      </FreshSWR>,
    );
    // attend la résolution
    await waitFor(() => expect(appsApi.getApps).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /apps/i })).toBeNull();
  });

  it('reste caché pendant le chargement initial', () => {
    vi.spyOn(appsApi, 'getApps').mockReturnValue(new Promise(() => {})); // never resolves
    render(
      <FreshSWR>
        <AppsMenu />
      </FreshSWR>,
    );
    expect(screen.queryByRole('button', { name: /apps/i })).toBeNull();
  });

  it('affiche le bouton quand au moins une app est dispo', async () => {
    vi.spyOn(appsApi, 'getApps').mockResolvedValue({
      urls: [
        {
          key: 'docker', label: 'Docker',
          icon: 'https://docker-agflow.yoops.org/favicon.ico',
          url: 'https://docker-agflow.yoops.org/',
        },
      ],
    });
    render(
      <FreshSWR>
        <AppsMenu />
      </FreshSWR>,
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /apps/i })).toBeInTheDocument();
    });
  });

  it('clic ouvre le menu et liste les apps avec target=_blank', async () => {
    vi.spyOn(appsApi, 'getApps').mockResolvedValue({
      urls: [
        {
          key: 'docker', label: 'Docker',
          icon: 'https://x.example/icon.ico',
          url: 'https://docker-agflow.yoops.org/',
        },
        {
          key: 'security', label: 'Security',
          icon: 'https://x.example/icon2.ico',
          url: 'https://security.yoops.org/',
        },
      ],
    });
    render(
      <FreshSWR>
        <AppsMenu />
      </FreshSWR>,
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /apps/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /apps/i }));

    const docker = await screen.findByRole('menuitem', { name: /docker/i });
    const security = screen.getByRole('menuitem', { name: /security/i });
    expect(docker).toHaveAttribute('href', 'https://docker-agflow.yoops.org/');
    expect(docker).toHaveAttribute('target', '_blank');
    expect(docker).toHaveAttribute('rel', 'noopener noreferrer');
    expect(security).toHaveAttribute('href', 'https://security.yoops.org/');
  });

  it('Escape ferme le menu', async () => {
    vi.spyOn(appsApi, 'getApps').mockResolvedValue({
      urls: [
        {
          key: 'docker', label: 'Docker',
          icon: 'https://x.example/icon.ico',
          url: 'https://docker-agflow.yoops.org/',
        },
      ],
    });
    render(
      <FreshSWR>
        <AppsMenu />
      </FreshSWR>,
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /apps/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /apps/i }));
    expect(await screen.findByRole('menuitem', { name: /docker/i })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByRole('menuitem', { name: /docker/i })).toBeNull();
    });
  });
});
