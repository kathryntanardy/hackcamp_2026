import type { MapRepo } from './types'

/** Match the gold health-score thresholds; unavailable scores stay unknown. */
export function healthTone(score: number | null): MapRepo['vulnerabilityTone'] {
  if (score == null || !Number.isFinite(score)) return 'none'
  if (score >= 70) return 'low'
  if (score >= 40) return 'medium'
  return 'high'
}
