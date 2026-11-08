import type { MapSearchScope } from '../components/MapSearchBar'
import type { RepoListItem } from '../components/RepoListSidebar'
import type { MapRepo } from './types'

/** Search repo names in every grouping, with the selected field as an extra match. */
export function localSearchIds(
  needle: string,
  mapRepos: MapRepo[],
  listRepos: RepoListItem[],
  scope: MapSearchScope,
): string[] {
  const q = needle.trim().toLowerCase()
  const listById = new Map(listRepos.map((repo) => [repo.id, repo]))
  const nameRank = (repo: MapRepo) => {
    const name = repo.name.toLowerCase()
    if (name === q) return 0
    if (name.startsWith(q)) return 1
    if (name.includes(q)) return 2
    return repo.id.toLowerCase().includes(q) ? 3 : 4
  }
  return mapRepos.filter((repo) => {
    const name = `${repo.name} ${repo.id}`.toLowerCase()
    const category = (repo.category || listById.get(repo.id)?.category || '').toLowerCase()
    const buckets = repo.vulnBuckets.join(' ').toLowerCase()
    if (scope === 'name') return name.includes(q)
    if (scope === 'category') return name.includes(q) || category.includes(q)
    if (scope === 'vulnerabilities') return name.includes(q) || buckets.includes(q)
    const description = listById.get(repo.id)?.description || ''
    return `${name} ${repo.language || ''} ${repo.overview} ${category} ${description} ${buckets}`
      .toLowerCase().includes(q)
  }).sort((a, b) => nameRank(a) - nameRank(b)).map((repo) => repo.id)
}

/** Semantic refinement must keep direct name matches and local field matches. */
export function mergeSearchIds(
  needle: string,
  mapRepos: MapRepo[],
  localIds: string[],
  semanticIds: string[],
): string[] {
  const names = new Set(localSearchIds(needle, mapRepos, [], 'name'))
  const corpusIds = new Set(mapRepos.map((repo) => repo.id))
  return [...new Set([
    ...localIds.filter((id) => names.has(id)),
    ...semanticIds,
    ...localIds,
  ])].filter((id) => corpusIds.has(id))
}

/** Preserve Vector Search ranking and keep autocomplete independent of flower pins. */
export function searchResultItems(repos: RepoListItem[], ids: string[] | null): RepoListItem[] {
  if (ids == null) return []
  const byId = new Map(repos.map((repo) => [repo.id, repo]))
  return [...new Set(ids)].flatMap((id) => {
    const repo = byId.get(id)
    return repo ? [repo] : []
  })
}
