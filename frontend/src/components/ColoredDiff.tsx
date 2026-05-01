'use client';

import type { FC } from 'react';
import ReactDiffViewerImport from 'react-diff-viewer-continued';

interface ReactDiffViewerLikeProps {
  oldValue: string;
  newValue: string;
  splitView?: boolean;
  leftTitle?: string;
  rightTitle?: string;
}

const ReactDiffViewer = ReactDiffViewerImport as unknown as FC<ReactDiffViewerLikeProps>;

export interface ColoredDiffProps {
  oldValue: string;
  newValue: string;
  leftTitle?: string;
  rightTitle?: string;
  splitView?: boolean;
}

export function ColoredDiff({
  oldValue,
  newValue,
  leftTitle,
  rightTitle,
  splitView = true,
}: ColoredDiffProps) {
  return (
    <ReactDiffViewer
      oldValue={oldValue}
      newValue={newValue}
      leftTitle={leftTitle}
      rightTitle={rightTitle}
      splitView={splitView}
    />
  );
}
