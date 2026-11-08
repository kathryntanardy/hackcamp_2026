import type { MapCamera, MapRepo, Point, WorldBounds } from './types'
import { FLOWER_SCENE } from './flowerScene'

export const MIN_SCALE = 0.1
// Figma "Zoomed in" (64:31629): the 269.309px flower becomes 909.212px.
// Every manual and programmatic camera operation shares this ceiling.
export const MAX_SCALE = 909.211669921875 / 269.30877685546875
export const ZOOM_STEP = 1.35
export const FIT_PADDING = 56

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

/** Screen-space gutters so focus/fit centers in the visible map, not under chrome. */
export type ViewInsets = {
  left?: number
  right?: number
  top?: number
  bottom?: number
}

function resolveInsets(insets?: ViewInsets) {
  return {
    left: Math.max(0, insets?.left ?? 0),
    right: Math.max(0, insets?.right ?? 0),
    top: Math.max(0, insets?.top ?? 0),
    bottom: Math.max(0, insets?.bottom ?? 0),
  }
}

/** The full branch design is the furthest-out view available. */
export function minScaleForViewport(width: number, height: number, insets?: ViewInsets): number {
  const i = resolveInsets(insets)
  return Math.min(maxScaleForViewport(width, height, insets), Math.max(MIN_SCALE,
    Math.min(Math.max(1, width - i.left - i.right) / FLOWER_SCENE.width,
      Math.max(1, height - i.top - i.bottom) / FLOWER_SCENE.height)))
}

/** Preserve the reference's framing in smaller windows and beside the drawer. */
export function maxScaleForViewport(width: number, height: number, insets?: ViewInsets): number {
  const i = resolveInsets(insets)
  const ratio = Math.min(1,
    Math.max(1, width - i.left - i.right) / FLOWER_SCENE.width,
    Math.max(1, height - i.top - i.bottom) / FLOWER_SCENE.height,
  )
  return Math.max(MIN_SCALE, MAX_SCALE * ratio)
}

/** Center of the content box after subtracting insets. */
export function contentCenter(
  width: number,
  height: number,
  insets?: ViewInsets,
): Point {
  const i = resolveInsets(insets)
  return {
    x: i.left + (width - i.left - i.right) / 2,
    y: i.top + (height - i.top - i.bottom) / 2,
  }
}

export function fitBounds(
  bounds: WorldBounds,
  width: number,
  height: number,
  padding = FIT_PADDING,
  insets?: ViewInsets,
): MapCamera {
  const i = resolveInsets(insets)
  const worldW = bounds.maxX - bounds.minX
  const worldH = bounds.maxY - bounds.minY
  const availW = Math.max(1, width - i.left - i.right - padding * 2)
  const availH = Math.max(1, height - i.top - i.bottom - padding * 2)
  const scale = clampScale(Math.min(availW / worldW, availH / worldH), maxScaleForViewport(width, height, insets), minScaleForViewport(width, height, insets))
  const cx = (bounds.minX + bounds.maxX) / 2
  const cy = (bounds.minY + bounds.maxY) / 2
  const screen = contentCenter(width, height, i)
  return {
    scale,
    offsetX: screen.x - cx * scale,
    offsetY: screen.y - cy * scale,
  }
}

export function clampScale(scale: number, ceiling = MAX_SCALE, floor = MIN_SCALE): number {
  return Math.min(ceiling, Math.max(floor, scale))
}

/** Zoom keeping the given screen point fixed in world space. */
export function zoomAt(
  camera: MapCamera,
  screen: Point,
  nextScale: number,
  ceiling = MAX_SCALE,
  floor = MIN_SCALE,
): MapCamera {
  const scale = clampScale(nextScale, ceiling, floor)
  if (scale === camera.scale) return camera
  const world = screenToWorld(screen, camera)
  return {
    scale,
    offsetX: screen.x - world.x * scale,
    offsetY: screen.y - world.y * scale,
  }
}

/** Apply both zoom limits, returning to the original framing at the lower limit. */
export function zoomForViewport(camera: MapCamera, screen: Point, nextScale: number, width: number, height: number): MapCamera {
  const floor = minScaleForViewport(width, height)
  if (nextScale < camera.scale && nextScale <= floor) {
    return fitBounds({ minX: 0, minY: 0, maxX: FLOWER_SCENE.width, maxY: FLOWER_SCENE.height }, width, height, 0)
  }
  return zoomAt(camera, screen, nextScale, maxScaleForViewport(width, height), floor)
}

export function panBy(camera: MapCamera, dx: number, dy: number): MapCamera {
  return {
    ...camera,
    offsetX: camera.offsetX + dx,
    offsetY: camera.offsetY + dy,
  }
}

/** Center a world point in the (inset-aware) viewport at the given scale. */
export function focusOn(
  point: Point,
  width: number,
  height: number,
  scale: number,
  insets?: ViewInsets,
): MapCamera {
  const s = clampScale(scale, maxScaleForViewport(width, height, insets), minScaleForViewport(width, height, insets))
  const screen = contentCenter(width, height, insets)
  return {
    scale: s,
    offsetX: screen.x - point.x * s,
    offsetY: screen.y - point.y * s,
  }
}

export function lerpCamera(from: MapCamera, to: MapCamera, t: number, ceiling = MAX_SCALE, floor = MIN_SCALE): MapCamera {
  const u = Math.min(1, Math.max(0, t))
  // Ease-out cubic.
  const e = 1 - (1 - u) ** 3
  return {
    scale: clampScale(from.scale + (to.scale - from.scale) * e, ceiling, floor),
    offsetX: from.offsetX + (to.offsetX - from.offsetX) * e,
    offsetY: from.offsetY + (to.offsetY - from.offsetY) * e,
  }
}
