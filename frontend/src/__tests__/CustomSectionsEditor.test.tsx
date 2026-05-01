import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CustomSectionsEditor } from '@/app/projects/[id]/role/CustomSectionsEditor';
import * as api from '@/lib/api/role-projects';

describe('CustomSectionsEditor (Phase 2 sous-projet G)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('rend la liste initiale et le champ d\'ajout', () => {
    render(
      <CustomSectionsEditor projectId="p1" initial={['Outils', 'Ton']} />,
    );
    expect(screen.getByText('Outils')).toBeInTheDocument();
    expect(screen.getByText('Ton')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/ex:/i)).toBeInTheDocument();
  });

  it('ajout d\'un nom valide appelle updateCustomSections avec la liste mise à jour', async () => {
    const spy = vi.spyOn(api, 'updateCustomSections').mockResolvedValue();
    render(<CustomSectionsEditor projectId="p1" initial={['Outils']} />);

    fireEvent.change(screen.getByPlaceholderText(/ex:/i), {
      target: { value: 'Style-redactionnel' },
    });
    fireEvent.click(screen.getByRole('button', { name: /ajouter/i }));

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith('p1', ['Outils', 'Style-redactionnel']),
    );
  });

  it('rejette un nom avec espace', async () => {
    const spy = vi.spyOn(api, 'updateCustomSections');
    render(<CustomSectionsEditor projectId="p1" initial={[]} />);

    fireEvent.change(screen.getByPlaceholderText(/ex:/i), {
      target: { value: 'avec espace' },
    });
    fireEvent.click(screen.getByRole('button', { name: /ajouter/i }));

    await waitFor(() => {
      expect(screen.getByText(/format invalide/i)).toBeInTheDocument();
    });
    expect(spy).not.toHaveBeenCalled();
  });

  it('rejette une collision avec section standard (Role)', async () => {
    const spy = vi.spyOn(api, 'updateCustomSections');
    render(<CustomSectionsEditor projectId="p1" initial={[]} />);

    fireEvent.change(screen.getByPlaceholderText(/ex:/i), {
      target: { value: 'Role' },
    });
    fireEvent.click(screen.getByRole('button', { name: /ajouter/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/section standard, pas custom/i),
      ).toBeInTheDocument();
    });
    expect(spy).not.toHaveBeenCalled();
  });

  it('clic Supprimer enlève l\'item et appelle l\'API', async () => {
    const spy = vi.spyOn(api, 'updateCustomSections').mockResolvedValue();
    render(
      <CustomSectionsEditor projectId="p1" initial={['Outils', 'Ton']} />,
    );

    const removeButtons = screen.getAllByRole('button', { name: /supprimer/i });
    fireEvent.click(removeButtons[0]!);

    await waitFor(() => expect(spy).toHaveBeenCalledWith('p1', ['Ton']));
  });

  it('désactive l\'input à la limite max (5 items)', () => {
    render(
      <CustomSectionsEditor
        projectId="p1"
        initial={['A1', 'A2', 'A3', 'A4', 'A5']}
      />,
    );
    const input = screen.getByPlaceholderText(/ex:/i) as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });
});
