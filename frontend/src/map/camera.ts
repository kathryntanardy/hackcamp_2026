import type { MapCamera, MapRepo, Point, WorldBounds } from './types'

export const MIN_SCALE = 1.5
export const MAX_SCALE = 48
export const ZOOM_STEP = 1.28
export const FIT_PADDING = 48

export function worldToScreen(point: Point, camera: MapCamera): Point {
  return {
    x: point.x * camera.scale + camera.offsetX,
    y: point.y * camera.scale + camera.offsetY,
  }
}

export function screenToWorld(point: Point, camera: MapCamera): Point {
  return {
    x: (point.x - camera.offsetX) / camera.scale,
    y: (point.y - camera.offsetY) / camera.scale,
  }
}

export function boundsOf(repos: Pick<MapRepo, 'x' | 'y'>[]): WorldBounds | null {
  if (repos.length === 0) return null
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const repo of repos) {
    if (repo.x < minX) minX = repo.x
    if (repo.x > maxX) maxX = repo.x
    if (repo.y < minY) minY = repo.y
    if (repo.y > maxY) maxY = repo.y
  }
  if (!Number.isFinite(minX)) return null
  // Avoid zero-size bounds when all points coincide.
  if (maxX - minX < 1) {
    minX -= 0.5
    maxX += 0.5
  }
  if (maxY - minY < 1) {
    minY -= 0.5
    maxY += 0.5
  }
  return { minX, maxX, minY, maxY }
}

export function fitBounds(
  bounds: WorldBounds,
  width: number,
  height: number,
  padding = FIT_PADDING,
): MapCamera {
  const worldW = bounds.maxX - bounds.minX
  const worldH = bounds.maxY - bounds.minY
  const availW = Math.max(1, width - padding * 2)
  const availH = Math.max(1, height - padding * 2)
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, Math.min(availW / worldW, availH / worldH)))
  const cx = (bounds.minX + bounds.maxX) / 2
  const cy = (bounds.minY + bounds.maxY) / 2
  return {
    scale,
    offsetX: width / 2 - cx * scale,
    offsetY: height / 2 - cy * scale,
  }
}

export function clampScale(scale: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale))
}

/** Zoom keeping the given screen point fixed in world space. */
export function zoomAt(
  camera: MapCamera,
  screen: Point,
  nextScale: number,
): MapCamera {
  const scale = clampScale(nextScale)
  if (scale === camera.scale) return camera
  const world = screenToWorld(screen, camera)
  return {
    scale,
    offsetX: screen.x - world.x * scale,
    offsetY: screen.y - world.y * scale,
  }
}

export function panBy(camera: MapCamera, dx: number, dy: number): MapCamera {
  return {
    ...camera,
    offsetX: camera.offsetX + dx,
    offsetY: camera.offsetY + dy,
  }
}
