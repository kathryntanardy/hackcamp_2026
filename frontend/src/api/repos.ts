import type { RepoDetail, RepoListEntry } from './types'

export async function fetchRepos(signal?: AbortSignal): Promise<RepoListEntry[]> {
  const res = await fetch('/api/repos', { signal })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(detail || `Failed to load repos (${res.status})`)
  }
  return res.json() as Promise<RepoListEntry[]>
}

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
