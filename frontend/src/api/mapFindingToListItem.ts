import { maintenanceStatusLabel } from '../map/health'
import type { RepoListItem } from '../components/RepoListSidebar'
import type { FindingListEntry } from './types'

/** Live risk_level values: at_risk | watchlist | healthy | inconclusive (| ignored, filtered in API). */
function riskTone(risk: string | null | undefined): RepoListItem['vulnerabilityTone'] {
  const r = (risk || '').toLowerCase()
  if (r === 'at_risk') return 'high'
  if (r === 'watchlist') return 'medium'
  if (r === 'healthy') return 'low'
  if (r === 'inconclusive') return 'none'
  return 'none'
}

export function mapFindingToListItem(finding: FindingListEntry): RepoListItem {
  const tone = riskTone(finding.risk_level)
  const confidence = Math.round((finding.confidence ?? 0) * 100)
  return {
    id: finding.repo_id,
    name: finding.name || finding.repo_id,
    description: finding.headline || finding.explanation || '',
    vulnerabilityLabel: maintenanceStatusLabel(finding.risk_level),
    vulnerabilityTone: tone,
    vulnerabilityScore: `${confidence}%`,
    category: finding.category?.trim() || finding.language || '—',
  }
}
