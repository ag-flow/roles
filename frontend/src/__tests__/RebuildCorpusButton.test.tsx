import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { RebuildCorpusButton } from '@/app/projects/[id]/corpus/RebuildCorpusButton';
import * as api from '@/lib/api/corpus';

describe('RebuildCorpusButton (Phase 2 sous-projet E)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('appelle rebuildCorpus si l\'utilisateur confirme', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const spy = vi.spyOn(api, 'rebuildCorpus').mockResolvedValue({
      deleted_chunks: 12,
      enqueued_jobs: 3,
    });

    render(<RebuildCorpusButton projectId="proj1" />);
    fireEvent.click(
      screen.getByRole('button', { name: /reconstruire le corpus/i }),
    );

    await waitFor(() => expect(spy).toHaveBeenCalledWith('proj1'));
    await waitFor(() => {
      expect(screen.getByText(/12 chunk\(s\) supprimé\(s\)/)).toBeInTheDocument();
      expect(screen.getByText(/3 job\(s\) re-mis en file/)).toBeInTheDocument();
    });
  });

  it('n\'appelle pas rebuildCorpus si l\'utilisateur annule', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const spy = vi.spyOn(api, 'rebuildCorpus');

    render(<RebuildCorpusButton projectId="proj1" />);
    fireEvent.click(
      screen.getByRole('button', { name: /reconstruire le corpus/i }),
    );

    await new Promise((r) => setTimeout(r, 10));
    expect(spy).not.toHaveBeenCalled();
  });

  it('affiche l\'erreur si rebuildCorpus échoue', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(api, 'rebuildCorpus').mockRejectedValue(new Error('500 boom'));

    render(<RebuildCorpusButton projectId="proj1" />);
    fireEvent.click(
      screen.getByRole('button', { name: /reconstruire le corpus/i }),
    );

    await waitFor(() => {
      expect(screen.getByText(/500 boom/)).toBeInTheDocument();
    });
  });
});
