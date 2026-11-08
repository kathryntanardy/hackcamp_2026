import type { RepoListItem } from '../components/RepoListSidebar'
import type { RepoListEntry } from './types'

function severityTone(
  severity: string | null | undefined,
  riskLevel: string | null | undefined,
): RepoListItem['vulnerabilityTone'] {
  const s = (severity || '').toLowerCase()
  if (s === 'critical' || s === 'high') return 'high'
  if (s === 'medium' || s === 'moderate') return 'medium'
  if (s === 'low') return 'low'

  const risk = (riskLevel || '').toLowerCase()
  if (risk === 'at_risk') return 'high'
  if (risk === 'watchlist') return 'medium'
  return 'none'
}

function severityLabel(tone: RepoListItem['vulnerabilityTone'], severity: string | null): string {
  if (tone === 'high') {
    if ((severity || '').toLowerCase() === 'critical') return 'Critical Vulnerability'
    return 'High Vulnerability'
  }
  if (tone === 'medium') return 'Medium Vulnerability'
  if (tone === 'low') return 'Low Vulnerability'
  return 'No advisories'
}

function formatScore(maxCvss: number | null | undefined): string {
  if (maxCvss == null || Number.isNaN(maxCvss)) return '—'
  const rounded = Math.round(maxCvss * 10) / 10
  const display = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
  return `${display}/10`
}

export function mapRepoToListItem(repo: RepoListEntry): RepoListItem {
  const tone = severityTone(repo.max_severity, repo.risk_level)
  return {
    id: repo.repo_id,
    name: repo.name || repo.repo_id,
    description: repo.summary?.trim() || '',
    vulnerabilityLabel: severityLabel(tone, repo.max_severity),
    vulnerabilityTone: tone,
    vulnerabilityScore: formatScore(repo.max_cvss),
    category: repo.category?.trim() || '—',
  }
}
