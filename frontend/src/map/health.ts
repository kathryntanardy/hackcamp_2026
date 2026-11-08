import type { MapRepo } from './types'

/** Match the gold health-score thresholds; unavailable scores stay unknown. */
export function healthTone(score: number | null): MapRepo['vulnerabilityTone'] {
  if (score == null || !Number.isFinite(score)) return 'none'
  if (score >= 70) return 'low'
  if (score >= 40) return 'medium'
  return 'high'
}

/** Display wording only; persisted status values and score thresholds stay unchanged. */
export function maintenanceStatusLabel(status: string | null | undefined): string {
  switch (status?.toLowerCase()) {
    case 'healthy': return 'Healthy'
    case 'watchlist': return 'Watchlist'
    case 'at_risk': return 'At Risk'
    case 'ignored': return 'Excluded'
    case 'inconclusive': return 'Inconclusive'
    default: return 'Unknown'
  }
}

export function maintenanceToneLabel(tone: 'high' | 'medium' | 'low'): string {
  return tone === 'low' ? 'Healthy' : tone === 'medium' ? 'Watchlist' : 'At Risk'
}

export const MAINTENANCE_HEALTH_DESCRIPTION =
  'Based on release freshness, commit trend, and recent push activity. Higher scores indicate more active maintenance, not a guarantee of security or code quality.'
