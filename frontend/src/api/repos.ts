import type { RepoDetail } from './types'

export async function fetchRepo(
  repoId: string,
  signal?: AbortSignal,
): Promise<RepoDetail> {
  const res = await fetch(`/api/repos/${repoId}`, { signal })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(detail || `Failed to load ${repoId} (${res.status})`)
  }
  return res.json() as Promise<RepoDetail>
}
