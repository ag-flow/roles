import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DocumentTree } from '@/app/projects/[id]/role/DocumentTree';
import type { RoleDocumentSummary } from '@/lib/types';

const sections: Record<string, RoleDocumentSummary[]> = {
  Role: [
    {
      id: 'd1',
      section: 'Role',
      name: 'principe-empathie',
      version: 2,
      is_current: true,
      locked: false,
      updated_at: '2026-04-29T10:00:00Z',
    },
    {
      id: 'd2',
      section: 'Role',
      name: 'biais-pragmatique',
      version: 1,
      is_current: true,
      locked: true,
      updated_at: '2026-04-28T10:00:00Z',
    },
  ],
  Missions: [],
};

describe('DocumentTree', () => {
  it('liste sections et documents', () => {
    render(<DocumentTree sections={sections} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('Role')).toBeInTheDocument();
    expect(screen.getByText('Missions')).toBeInTheDocument();
    expect(screen.getByText('principe-empathie')).toBeInTheDocument();
    expect(screen.getByText('biais-pragmatique')).toBeInTheDocument();
  });

  it('clic sur un document appelle onSelect avec son id', () => {
    const onSelect = vi.fn();
    render(<DocumentTree sections={sections} selectedId={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByText('principe-empathie'));
    expect(onSelect).toHaveBeenCalledWith('d1');
  });

  it('marque la section vide comme empty', () => {
    render(<DocumentTree sections={sections} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByText(/aucun document/i)).toBeInTheDocument();
  });

  it('affiche un cadenas pour les documents verrouillés', () => {
    render(<DocumentTree sections={sections} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByLabelText(/verrouillé/i)).toBeInTheDocument();
  });

  it('met en évidence le document sélectionné', () => {
    const { container } = render(
      <DocumentTree sections={sections} selectedId="d1" onSelect={vi.fn()} />,
    );
    const selectedButton = container.querySelector('button[data-selected="true"]');
    expect(selectedButton).not.toBeNull();
    expect(selectedButton?.textContent).toContain('principe-empathie');
  });

  it('affiche le numéro de version à côté du nom', () => {
    render(<DocumentTree sections={sections} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('v2')).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();
  });
});
