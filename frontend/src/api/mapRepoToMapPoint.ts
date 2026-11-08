import type { MapRepo, MapStatus } from '../map/types'
import type { RepoListEntry } from './types'

function normalizeStatus(status: string | null | undefined): MapStatus {
  const s = (status || '').toLowerCase()
  if (s === 'healthy') return 'healthy'
  if (s === 'watchlist') return 'watchlist'
  if (s === 'at_risk') return 'at_risk'
  if (s === 'ignored') return 'ignored'
  return 'unknown'
}

function formatScore(maxCvss: number | null | undefined): string {
  if (maxCvss == null || Number.isNaN(maxCvss)) return '—'
  const rounded = Math.round(maxCvss * 10) / 10
  const display = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
  return `${display}/10`
}

function severityTone(
  severity: string | null | undefined,
  riskLevel: string | null | undefined,
): MapRepo['vulnerabilityTone'] {
  const s = (severity || '').toLowerCase()
  if (s === 'critical' || s === 'high') return 'high'
  if (s === 'medium' || s === 'moderate') return 'medium'
  if (s === 'low') return 'low'

  const risk = (riskLevel || '').toLowerCase()
  if (risk === 'at_risk') return 'high'
  if (risk === 'watchlist') return 'medium'
  return 'none'
}

export function mapRepoToMapPoint(repo: RepoListEntry): MapRepo | null {
  if (repo.x == null || repo.y == null || Number.isNaN(repo.x) || Number.isNaN(repo.y)) {
    return null
  }
  return {
    id: repo.repo_id,
    name: repo.name || repo.repo_id,
    overview: repo.summary?.trim() || '',
    language: repo.language,
    status: normalizeStatus(repo.status),
    importance: repo.importance ?? 0,
    x: repo.x,
    y: repo.y,
    catX: repo.cat_x ?? repo.x,
    catY: repo.cat_y ?? repo.y,
    vulnerabilityScore: formatScore(repo.max_cvss),
    vulnerabilityTone: severityTone(repo.max_severity, repo.risk_level),
    investigatedInLatestRun: Boolean(repo.investigated_in_latest_run),
  }
}
