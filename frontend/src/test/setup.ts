import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Auto-cleanup React Testing Library entre tests :
// `globals: false` dans vitest.config.ts désactive le cleanup implicite.
afterEach(() => {
  cleanup();
});
