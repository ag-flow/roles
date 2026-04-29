import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PushPreview } from '@/app/projects/[id]/role/PushPreview';
import type { PushPreview as PushPreviewT } from '@/lib/types';

const baseFixture: PushPreviewT = {
  display_name: 'UX Designer Clea',
  description: null,
  identity_length: 1500,
  target_role_id: null,
  sections: [
    {
      name: 'Role',
      documents: [
        { name: 'principe-empathie', size: 1200 },
        { name: 'biais-pragmatique', size: 1100 },
      ],
    },
    {
      name: 'Missions',
      documents: [{ name: 'audit-ux', size: 800 }],
    },
  ],
  ready_to_push: true,
  missing: [],
};

describe('PushPreview', () => {
  it('affiche les sections et leurs documents', () => {
    render(<PushPreview preview={baseFixture} />);
    expect(screen.getByText('Role')).toBeInTheDocument();
    expect(screen.getByText('Missions')).toBeInTheDocument();
    expect(screen.getByText('principe-empathie')).toBeInTheDocument();
    expect(screen.getByText('biais-pragmatique')).toBeInTheDocument();
    expect(screen.getByText('audit-ux')).toBeInTheDocument();
  });

  it('affiche la longueur d\'identity', () => {
    render(<PushPreview preview={baseFixture} />);
    // Le compteur est dans un <strong> enfant d'un <p>, on cible le <strong>
    expect(screen.getByText('1500 caractères')).toBeInTheDocument();
  });

  it('affiche les éléments manquants quand ready_to_push=false', () => {
    const notReady: PushPreviewT = {
      ...baseFixture,
      ready_to_push: false,
      missing: [
        'Identity not generated',
        "Section 'Skills' has no current documents",
      ],
    };
    render(<PushPreview preview={notReady} />);
    expect(screen.getByText('Identity not generated')).toBeInTheDocument();
    expect(
      screen.getByText("Section 'Skills' has no current documents"),
    ).toBeInTheDocument();
    expect(screen.getByText(/manquant/i)).toBeInTheDocument();
  });

  it('affiche le target_role_id si déjà poussé', () => {
    const pushed: PushPreviewT = {
      ...baseFixture,
      target_role_id: 'role-abc-123',
    };
    render(<PushPreview preview={pushed} />);
    expect(screen.getByText(/role-abc-123/)).toBeInTheDocument();
  });

  it('n\'affiche pas la section "déjà poussé" si target_role_id null', () => {
    render(<PushPreview preview={baseFixture} />);
    expect(screen.queryByText(/déjà poussé/i)).not.toBeInTheDocument();
  });
});
