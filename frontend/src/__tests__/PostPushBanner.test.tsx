import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PostPushBanner } from '@/app/projects/[id]/role/PostPushBanner';
import * as exportApi from '@/lib/api/agflow-export';
import type { PushToAgflowResponse } from '@/lib/types';

const baseResult: PushToAgflowResponse = {
  agflow_role_id: 'r-abc-123',
  zip_size_bytes: 102_400,
  documents_count: 7,
  prompt_generated: true,
  agflow_url: 'https://docker-agflow.yoops.org/admin/roles/r-abc-123',
};

describe('PostPushBanner', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('banner vert avec lien admin quand tout OK', () => {
    const { container } = render(
      <PostPushBanner
        projectId="p1"
        result={baseResult}
        partialFailure={null}
        onDismiss={vi.fn()}
      />,
    );
    // Border-left vert (#16a34a) — on cherche le style style="border-left: ..."
    const banner = container.firstChild as HTMLElement;
    expect(banner.style.borderLeft).toContain('rgb(22, 163, 74)');
    expect(screen.getByText(/Rôle poussé sur ag\.flow/i)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /admin ag\.flow/i });
    expect(link).toHaveAttribute('href', baseResult.agflow_url);
  });

  it('banner rouge + bouton "Réessayer" quand échec partiel sur prompt', () => {
    const { container } = render(
      <PostPushBanner
        projectId="p1"
        result={{ ...baseResult, prompt_generated: false }}
        partialFailure="prompt"
        onDismiss={vi.fn()}
      />,
    );
    const banner = container.firstChild as HTMLElement;
    expect(banner.style.borderLeft).toContain('rgb(220, 38, 38)');
    expect(
      screen.getByText(/génération du prompt a échoué/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Réessayer la génération/i }),
    ).toBeInTheDocument();
  });

  it('clic sur "Réessayer" appelle generatePromptsOnAgflow et dismiss au succès', async () => {
    const spy = vi
      .spyOn(exportApi, 'generatePromptsOnAgflow')
      .mockResolvedValue({ status: 'generated', target_role_id: 'r-abc-123' });
    const dismiss = vi.fn();

    render(
      <PostPushBanner
        projectId="p1"
        result={{ ...baseResult, prompt_generated: false }}
        partialFailure="prompt"
        onDismiss={dismiss}
      />,
    );
    fireEvent.click(
      screen.getByRole('button', { name: /Réessayer la génération/i }),
    );
    await waitFor(() => expect(spy).toHaveBeenCalledWith('p1'));
    await waitFor(() => expect(dismiss).toHaveBeenCalled());
  });

  it('affiche un message d\'erreur si retry échoue', async () => {
    vi.spyOn(exportApi, 'generatePromptsOnAgflow').mockRejectedValue(
      new Error('502 Bad Gateway'),
    );
    const dismiss = vi.fn();

    render(
      <PostPushBanner
        projectId="p1"
        result={{ ...baseResult, prompt_generated: false }}
        partialFailure="prompt"
        onDismiss={dismiss}
      />,
    );
    fireEvent.click(
      screen.getByRole('button', { name: /Réessayer la génération/i }),
    );
    await waitFor(() => {
      expect(screen.getByText(/502 Bad Gateway/i)).toBeInTheDocument();
    });
    expect(dismiss).not.toHaveBeenCalled();
  });
});
