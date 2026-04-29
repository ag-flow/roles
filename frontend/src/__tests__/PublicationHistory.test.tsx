import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import type { ReactNode } from 'react';
import { PublicationHistory } from '@/app/projects/[id]/role/PublicationHistory';
import * as gh from '@/lib/api/github';

function FreshSWR({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      {children}
    </SWRConfig>
  );
}

describe('PublicationHistory', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('liste les publications avec commit court + lien GitHub', async () => {
    vi.spyOn(gh, 'listPublications').mockResolvedValue([
      {
        id: 'p1',
        role_project_id: 'rp1',
        user_id: 'u',
        commit_sha: 'abcdef1234567890',
        published_at: '2026-04-29T10:00:00Z',
        files_count: 5,
        summary: 'Pushed to alice/roles/ux-clea',
      },
    ]);
    render(
      <FreshSWR>
        <PublicationHistory projectId="rp1" repoFullName="alice/roles" />
      </FreshSWR>,
    );
    await waitFor(() => {
      expect(screen.getByText(/abcdef1/)).toBeInTheDocument();
    });
    expect(
      screen.getByText(/Pushed to alice\/roles\/ux-clea/),
    ).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /abcdef1/ });
    expect(link).toHaveAttribute(
      'href',
      'https://github.com/alice/roles/commit/abcdef1234567890',
    );
  });

  it('empty state quand aucune publication', async () => {
    vi.spyOn(gh, 'listPublications').mockResolvedValue([]);
    render(
      <FreshSWR>
        <PublicationHistory projectId="rp1" repoFullName="alice/roles" />
      </FreshSWR>,
    );
    await waitFor(() => {
      expect(screen.getByText(/aucune publication/i)).toBeInTheDocument();
    });
  });

  it('sans repoFullName, le sha est affiché en code mais pas comme lien', async () => {
    vi.spyOn(gh, 'listPublications').mockResolvedValue([
      {
        id: 'p1',
        role_project_id: 'rp1',
        user_id: 'u',
        commit_sha: 'abc123def',
        published_at: '2026-04-29T10:00:00Z',
        files_count: 3,
        summary: null,
      },
    ]);
    render(
      <FreshSWR>
        <PublicationHistory projectId="rp1" repoFullName={null} />
      </FreshSWR>,
    );
    await waitFor(() => {
      expect(screen.getByText(/abc123d/)).toBeInTheDocument();
    });
    // Pas de lien
    expect(screen.queryByRole('link')).toBeNull();
  });
});
