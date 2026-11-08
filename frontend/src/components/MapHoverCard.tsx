import type { MapRepo } from '../map/types'

export type MapHoverCardProps = {
  repo: MapRepo
  x: number
  y: number
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
          className={`map-hover-card__swatch is-${repo.vulnerabilityTone}`}
          aria-hidden="true"
        />
        <span className="map-hover-card__name">{repo.name}</span>
      </div>
      {repo.flowerId ? (
        <p className="map-hover-card__bucket">{repo.flowerId}</p>
      ) : null}
      {repo.overview ? (
        <p className="map-hover-card__overview">{repo.overview}</p>
      ) : (
        <p className="map-hover-card__overview is-empty">No overview available.</p>
      )}
      <p className="map-hover-card__score">
        <span className="map-hover-card__score-label">Vulnerability Score:</span>{' '}
        <span
          className={`map-hover-card__score-value${
            repo.vulnerabilityTone === 'high' ? ' is-danger' : ''
          }`}
        >
          {repo.vulnerabilityScore}
        </span>
      </p>
    </div>
  )
}
