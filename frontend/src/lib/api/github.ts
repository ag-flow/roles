import { api, ApiError } from './client';
import type {
  GithubIntegrationStatus,
  GithubRepo,
  Publication,
  PublicationConfig,
  PublicationConfigRequest,
  PublishResponse,
} from '../types';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function getStatus(): Promise<GithubIntegrationStatus> {
  return api<GithubIntegrationStatus>('/api/auth/github/status');
}

export async function startOAuth(): Promise<{ redirect_url: string }> {
  return api<{ redirect_url: string }>('/api/auth/github/start');
}

export async function disconnect(): Promise<{ status: string }> {
  return api<{ status: string }>('/api/auth/github', { method: 'DELETE' });
}

export async function listRepos(): Promise<GithubRepo[]> {
  return api<GithubRepo[]>('/api/github/repos');
}

export async function getPublicationConfig(
  projectId: string,
): Promise<PublicationConfig | null> {
  try {
    return await api<PublicationConfig>(
      `/api/role-projects/${projectId}/publication-config`,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

export async function setPublicationConfig(
  projectId: string,
  body: PublicationConfigRequest,
): Promise<{ status: string }> {
  return api<{ status: string }>(
    `/api/role-projects/${projectId}/publication-config`,
    { method: 'PUT', body: JSON.stringify(body) },
  );
}

export async function publishToGithub(
  projectId: string,
): Promise<PublishResponse> {
  return api<PublishResponse>(
    `/api/role-projects/${projectId}/publish-to-github`,
    { method: 'POST' },
  );
}

export async function unpublishFromGithub(
  projectId: string,
): Promise<{ deleted_files: number }> {
  return api<{ deleted_files: number }>(
    `/api/role-projects/${projectId}/github-publication`,
    { method: 'DELETE' },
  );
}

export async function listPublications(
  projectId: string,
): Promise<Publication[]> {
  return api<Publication[]>(`/api/role-projects/${projectId}/publications`);
}

/** URL absolue de l'admin GitHub d'un repo (utile pour <a href={...}>). */
export function repoBrowseUrl(repoFullName: string, branch: string): string {
  return `https://github.com/${repoFullName}/tree/${branch}`;
}

export { API_BASE };
