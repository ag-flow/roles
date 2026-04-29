import { api } from './client';
import pkg from '../../../package.json';

export interface VersionInfo {
  version: string;
  name: string;
}

export async function getBackendVersion(): Promise<VersionInfo> {
  return api<VersionInfo>('/api/version');
}

/** Version frontend lue à la compilation depuis package.json. */
export function getFrontendVersion(): string {
  return (pkg as { version?: string }).version ?? '0.0.0';
}
