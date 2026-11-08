import { maintenanceStatusLabel } from '../map/health'
import type { RepoListItem } from '../components/RepoListSidebar'
import type { RepoListEntry } from './types'

/** High / Med / Low follow gold.status (same as the map), not advisory max_severity. */
function statusTone(status: string | null | undefined): RepoListItem['vulnerabilityTone'] {
  const s = (status || '').toLowerCase()
  if (s === 'at_risk') return 'high'
  if (s === 'watchlist') return 'medium'
  if (s === 'healthy') return 'low'
  return 'none'
}

function formatHealthScore(score: number | null | undefined): string {
  if (score == null || Number.isNaN(score)) return '—'
  return `${Math.round(score)}/100`
}

export function mapRepoToListItem(repo: RepoListEntry): RepoListItem {
  const tone = statusTone(repo.status)
  return {
    id: repo.repo_id,
    name: repo.name || repo.repo_id,
    description: repo.summary?.trim() || '',
    vulnerabilityLabel: maintenanceStatusLabel(repo.status),
    vulnerabilityTone: tone,
    vulnerabilityScore: formatHealthScore(repo.health_score),
    category: repo.category?.trim() || '—',
  }
}
