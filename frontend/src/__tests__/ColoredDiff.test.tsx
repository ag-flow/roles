import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ColoredDiff } from '@/components/ColoredDiff';

vi.mock('react-diff-viewer-continued', () => ({
  default: ({
    oldValue,
    newValue,
    leftTitle,
    rightTitle,
    splitView,
  }: {
    oldValue: string;
    newValue: string;
    leftTitle?: string;
    rightTitle?: string;
    splitView?: boolean;
  }) => (
    <div data-testid="diff-viewer" data-split={String(splitView ?? '')}>
      <span data-testid="old">{oldValue}</span>
      <span data-testid="new">{newValue}</span>
      {leftTitle && <span data-testid="left-title">{leftTitle}</span>}
      {rightTitle && <span data-testid="right-title">{rightTitle}</span>}
    </div>
  ),
}));

describe('ColoredDiff', () => {
  it('rend les deux contenus old/new', () => {
    render(<ColoredDiff oldValue="abc def" newValue="abc xyz" />);
    expect(screen.getByTestId('old')).toHaveTextContent('abc def');
    expect(screen.getByTestId('new')).toHaveTextContent('abc xyz');
  });

  it('rend les leftTitle / rightTitle', () => {
    render(
      <ColoredDiff
        oldValue="a"
        newValue="b"
        leftTitle="v1"
        rightTitle="v2"
      />,
    );
    expect(screen.getByTestId('left-title')).toHaveTextContent('v1');
    expect(screen.getByTestId('right-title')).toHaveTextContent('v2');
  });

  it('passe splitView=true par défaut', () => {
    render(<ColoredDiff oldValue="a" newValue="b" />);
    expect(screen.getByTestId('diff-viewer')).toHaveAttribute(
      'data-split',
      'true',
    );
  });

  it('ne crash pas sur strings vides', () => {
    render(<ColoredDiff oldValue="" newValue="" />);
    expect(screen.getByTestId('diff-viewer')).toBeInTheDocument();
  });
});
