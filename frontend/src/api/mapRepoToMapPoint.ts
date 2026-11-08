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

/** Map High/Med/Low to maintainer risk so "High" = most vulnerable (at risk). */
function severityTone(status: MapStatus): MapRepo['vulnerabilityTone'] {
  if (status === 'at_risk') return 'high'
  if (status === 'watchlist') return 'medium'
  if (status === 'healthy') return 'low'
  return 'none'
}

/** Normalize UC / mangled array payloads into clean bucket names. */
export function normalizeVulnBuckets(raw: unknown): string[] {
  if (raw == null) return []
  if (typeof raw === 'string') {
    const text = raw.trim()
    if (!text) return []
    if (text.startsWith('[')) {
      try {
        return normalizeVulnBuckets(JSON.parse(text))
      } catch {
        try {
          // Python-repr arrays from the warehouse: ['Code execution']
          const asJson = text.replace(/'/g, '"')
          return normalizeVulnBuckets(JSON.parse(asJson))
        } catch {
          return []
        }
      }
    }
    return [text]
  }
  if (!Array.isArray(raw)) return [String(raw)].filter(Boolean)
  if (raw.length > 0 && raw.every((x) => typeof x === 'string' && x.length <= 1)) {
    return normalizeVulnBuckets(raw.join(''))
  }
  const out: string[] = []
  for (const item of raw) {
    if (typeof item === 'string' && item.trim().startsWith('[')) {
      out.push(...normalizeVulnBuckets(item))
      continue
    }
    const text = String(item ?? '').trim()
    if (text) out.push(text)
  }
  return out
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
    category: repo.category?.trim() || null,
    status: normalizeStatus(repo.status),
    importance: repo.importance ?? 0,
    healthScore: repo.health_score == null || Number.isNaN(repo.health_score)
      ? null
      : repo.health_score,
    x: repo.x,
    y: repo.y,
    catX: repo.cat_x ?? repo.x,
    catY: repo.cat_y ?? repo.y,
    vulnerabilityScore: formatScore(repo.max_cvss),
    vulnerabilityTone: severityTone(normalizeStatus(repo.status)),
    vulnBuckets: normalizeVulnBuckets(repo.vuln_buckets),
    investigated: Boolean(repo.investigated),
    investigatedInLatestRun: Boolean(repo.investigated_in_latest_run),
  }
}
