import { worldToScreen } from './camera'
import type { MapCamera, MapRepo, MapStatus } from './types'

const STATUS_FILL: Record<MapStatus, string> = {
  healthy: '#2f9e6b',
  watchlist: '#d4a017',
  at_risk: '#c20c0c',
  ignored: '#a2a2a2',
  unknown: '#8a8a8a',
}

export function statusColor(status: MapStatus): string {
  return STATUS_FILL[status]
}

export function pointRadius(importance: number, scale: number): number {
  const base = 2.4 + Math.min(4.5, Math.max(0, importance) * 1.35)
  return Math.min(10, Math.max(2.2, base * Math.pow(scale / 6, 0.15)))
}

export function drawMap(
  ctx: CanvasRenderingContext2D,
  repos: MapRepo[],
  camera: MapCamera,
  selectedId: string | null,
  hoveredId: string | null,
  width: number,
  height: number,
): void {
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = '#fafafa'
  ctx.fillRect(0, 0, width, height)

  // Soft vignette so the field feels like a surface, not a blank page.
  const gradient = ctx.createRadialGradient(
    width * 0.5,
    height * 0.45,
    Math.min(width, height) * 0.1,
    width * 0.5,
    height * 0.5,
    Math.max(width, height) * 0.72,
  )
  gradient.addColorStop(0, 'rgba(252, 105, 78, 0.035)')
  gradient.addColorStop(1, 'rgba(250, 250, 250, 0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, width, height)

  for (const repo of repos) {
    const screen = worldToScreen({ x: repo.x, y: repo.y }, camera)
    if (
      screen.x < -20 ||
      screen.y < -20 ||
      screen.x > width + 20 ||
      screen.y > height + 20
    ) {
      continue
    }

    const radius = pointRadius(repo.importance, camera.scale)
    const isSelected = repo.id === selectedId
    const isHovered = repo.id === hoveredId

    if (isSelected || isHovered) {
      ctx.beginPath()
      ctx.arc(screen.x, screen.y, radius + (isSelected ? 5 : 3.5), 0, Math.PI * 2)
      ctx.strokeStyle = isSelected ? '#fc5239' : 'rgba(30, 30, 30, 0.35)'
      ctx.lineWidth = isSelected ? 2 : 1.25
      ctx.stroke()
    }

    if (repo.investigatedInLatestRun) {
      ctx.beginPath()
      ctx.arc(screen.x, screen.y, radius + 3, 0, Math.PI * 2)
      ctx.strokeStyle = 'rgba(252, 82, 57, 0.45)'
      ctx.lineWidth = 1
      ctx.stroke()
    }

    ctx.beginPath()
    ctx.arc(screen.x, screen.y, radius, 0, Math.PI * 2)
    ctx.fillStyle = statusColor(repo.status)
    ctx.fill()
  }
}

/** Nearest repo within hit pixels, or null. */
export function hitTest(
  repos: MapRepo[],
  camera: MapCamera,
  screenX: number,
  screenY: number,
  hitSlop = 8,
): MapRepo | null {
  let best: MapRepo | null = null
  let bestDist = Infinity
  for (const repo of repos) {
    const screen = worldToScreen({ x: repo.x, y: repo.y }, camera)
    const radius = pointRadius(repo.importance, camera.scale) + hitSlop
    const dx = screen.x - screenX
    const dy = screen.y - screenY
    const dist = Math.hypot(dx, dy)
    if (dist <= radius && dist < bestDist) {
      best = repo
      bestDist = dist
    }
  }
  return best
}
