import type { MapRepo } from '../map/types'
import { statusColor } from '../map/draw'

export type MapHoverCardProps = {
  repo: MapRepo
  x: number
  y: number
}

function formatHealthScore(score: number | null): string {
  if (score == null || Number.isNaN(score)) return '—'
  const rounded = Math.round(score * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}

function statusLabel(status: MapRepo['status']): string {
  return status.replaceAll('_', ' ')
}

export function MapHoverCard({ repo, x, y }: MapHoverCardProps) {
  return (
    <div
      className="map-hover-card"
      style={{ left: x, top: y }}
      role="tooltip"
    >
      <div className="map-hover-card__chip">
        <span
          className="map-hover-card__swatch"
          style={{ background: statusColor(repo.status) }}
          aria-hidden="true"
        />
        <span className="map-hover-card__name">{repo.name}</span>
      </div>
      <p className="map-hover-card__meta">
        <span className="map-hover-card__meta-label">Score</span>
        <span className="map-hover-card__meta-value">
          {formatHealthScore(repo.healthScore)}
        </span>
      </p>
      <p className="map-hover-card__meta">
        <span className="map-hover-card__meta-label">Status</span>
        <span className={`map-hover-card__status is-${repo.status}`}>
          {statusLabel(repo.status)}
        </span>
      </p>
    </div>
  )
}
