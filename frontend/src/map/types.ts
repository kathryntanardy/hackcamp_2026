export type MapStatus = 'healthy' | 'watchlist' | 'at_risk' | 'ignored' | 'unknown'

export type MapRepo = {
  id: string
  name: string
  overview: string
  language: string | null
  category: string | null
  status: MapStatus
  importance: number
  healthScore: number | null
  /** Language-cluster world coords from gold (x, y). */
  x: number
  y: number
  /** Category-cluster world coords from gold (cat_x, cat_y). */
  catX: number
  catY: number
  vulnerabilityScore: string
  vulnerabilityTone: 'high' | 'medium' | 'low' | 'none'
  vulnBuckets: string[]
  flowerId?: string
  investigated: boolean
  investigatedInLatestRun: boolean
}

export type MapCamera = {
  scale: number
  offsetX: number
  offsetY: number
}

export type Point = { x: number; y: number }

export type WorldBounds = {
  minX: number
  maxX: number
  minY: number
  maxY: number
}
