import { MAX_SCALE, worldToScreen } from './camera'
import { drawFlowerBloom, drawFlowerBranches } from './flowerBloom'
import {
  FLOWER_PALETTE,
  SEVERITY_GLYPH,
  type FlowerCluster,
  type SeverityFocus,
} from './flowers'
import { dispersePoint, growFactor } from './hoverAnim'
import { healthTone } from './health'
import { branchOpacities, flowerSlotOpacities, type FlowerPresence } from './flowerPresence'
import type { MapCamera, MapRepo, MapStatus } from './types'

const STATUS_FILL: Record<MapStatus, string> = {
  healthy: '#2f9e6b',
  watchlist: '#d4a017',
  at_risk: '#c20c0c',
  ignored: '#a2a2a2',
  unknown: '#8a8a8a',
}

/** Reveal health colors at medium zoom; overview stars stay white in all states. */
export const HEALTH_COLOR_MIN_SCALE = 1

/** Largest x cell in the Figma zoomed-in reference, including hover growth. */
export const MAX_GLYPH_PX = 25.58018684387207

export function statusColor(status: MapStatus): string {
  return STATUS_FILL[status]
}

/** World-space glyph size — screen px = this × camera.scale × grow. */
export function worldGlyphSize(importance: number): number {
  return 2.6 + Math.min(3.4, Math.max(0, importance) * 0.7)
}

export function xFontSize(importance: number, scale: number, grow = 1, glyphSize?: number): number {
  const px = (glyphSize ?? worldGlyphSize(importance)) * scale * grow
  return Math.min(MAX_GLYPH_PX, Math.max(glyphSize == null ? 4 : 0.75, px))
}

export function pointRadius(importance: number, scale: number, grow = 1, glyphSize?: number): number {
  return xFontSize(importance, scale, grow, glyphSize) * 0.55
}

function isOnScreen(
  screen: { x: number; y: number },
  pad: number,
  width: number,
  height: number,
): boolean {
  return !(
    screen.x < -pad ||
    screen.y < -pad ||
    screen.x > width + pad ||
    screen.y > height + pad
  )
}

function glyphColor(
  repo: MapRepo,
  scale: number,
  severityFocus: SeverityFocus | null,
  matchIds: ReadonlySet<string> | null,
  maxScale: number,
): { fill: string; dim: boolean; lit: boolean } {
  const base = scale < Math.min(HEALTH_COLOR_MIN_SCALE, maxScale / 2)
    ? '#ffffff'
    : SEVERITY_GLYPH[healthTone(repo.healthScore)]

  let dim = false
  let lit = false

  if (severityFocus) {
    const onFocusedFlower = repo.flowerId === severityFocus.flowerId
    if (!onFocusedFlower) {
      dim = true
    } else if (severityFocus.tone == null) {
      dim = false
    } else if (repo.vulnerabilityTone === severityFocus.tone) {
      lit = true
    } else {
      dim = true
    }
  }

  // Search matches dim non-hits (and can stack with severity dimming).
  if (matchIds) {
    if (matchIds.has(repo.id)) lit = true
    else dim = true
  }

  if (severityFocus?.tone != null && dim) {
    return { fill: '#ffffff', dim: false, lit: false }
  }
  return { fill: base, dim, lit }
}

export function drawMap(
  ctx: CanvasRenderingContext2D,
  repos: MapRepo[],
  flowers: FlowerCluster[],
  camera: MapCamera,
  selectedId: string | null,
  hoveredId: string | null,
  hoverAmount: number,
  width: number,
  height: number,
  severityFocus: SeverityFocus | null = null,
  matchIds: ReadonlySet<string> | null = null,
  maxScale = MAX_SCALE,
  presence?: FlowerPresence[],
): void {
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = '#f8f8f8'
  ctx.fillRect(0, 0, width, height)

  const hoverRepo = hoveredId ? repos.find((r) => r.id === hoveredId) ?? null : null
  const selectedRepo = selectedId
    ? repos.find((r) => r.id === selectedId) ?? null
    : null
  // Selection keeps neighbours slightly displaced; hover takes over the focus.
  const focusRepo = hoverRepo ?? selectedRepo
  const amount = focusRepo ? hoverAmount : 0

  const matchingFlowers = matchIds == null ? null : new Set(
    repos.filter(repo => matchIds.has(repo.id)).map(repo => repo.flowerId),
  )
  const visibleFlowers = presence ?? flowers.map((flower) => ({ flower, opacity: 1 }))
  drawFlowerBranches(ctx, camera, branchOpacities(visibleFlowers))
  const bloomVisibility = visibleFlowers.map(({ flower, opacity }) => {
    const dimOutside =
      (severityFocus != null && severityFocus.flowerId !== flower.id) ||
      (matchingFlowers != null && !matchingFlowers.has(flower.id))
    return { flower, opacity: opacity * (dimOutside ? 0.4 : 1) }
  })
  // A category change reuses the same petal artwork. Draw each slot once so
  // two half-transparent copies do not make the whole scene flash dimmer.
  for (const [slot, opacity] of flowerSlotOpacities(bloomVisibility)) {
    drawFlowerBloom(ctx, slot, camera, opacity)
  }

  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'

  const visibleRepos = presence
    ? presence.flatMap((entry) => entry.repos.map((repo) => ({ repo, opacity: entry.opacity })))
    : repos.map((repo) => ({ repo, opacity: 1 }))
  const ordered = visibleRepos.sort((a, b) => {
    const rank = (id: string) =>
      id === hoveredId ? 2 : id === selectedId ? 1 : 0
    return rank(a.repo.id) - rank(b.repo.id)
  })

  const screens: {
    repo: MapRepo
    screen: { x: number; y: number }
    size: number
    fill: string
    dim: boolean
    lit: boolean
    opacity: number
  }[] = []
  for (const { repo, opacity } of ordered) {
    const world = dispersePoint(repo, focusRepo, amount)
    const screen = worldToScreen(world, camera)
    const isSelected = repo.id === selectedId
    const isHovered = repo.id === hoveredId
    const { fill, dim, lit } = glyphColor(repo, camera.scale, severityFocus, matchIds, maxScale)
    const grow = growFactor(isHovered, isSelected, amount) * (lit ? 1.12 : 1)
    const size = xFontSize(repo.importance, camera.scale, grow, repo.glyphSize)
    if (!isOnScreen(screen, size, width, height)) continue
    screens.push({ repo, screen, size, fill, dim, lit, opacity })
  }

  for (const { repo, screen, size, fill, dim, lit, opacity } of screens) {
    const isSelected = repo.id === selectedId
    const isHovered = repo.id === hoveredId

    ctx.save()
    ctx.globalAlpha = opacity * (dim ? 0.28 : 1)

    ctx.font = `${isHovered || isSelected || lit ? 800 : 700} ${size}px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`

    ctx.fillStyle = fill
    ctx.fillText('x', screen.x, screen.y + size * 0.04)
    ctx.restore()
  }
}

export function hitTest(
  repos: MapRepo[],
  camera: MapCamera,
  screenX: number,
  screenY: number,
  hitSlop = 14,
): MapRepo | null {
  let best: MapRepo | null = null
  let bestDist = Infinity
  for (const repo of repos) {
    const screen = worldToScreen({ x: repo.x, y: repo.y }, camera)
    const radius = pointRadius(repo.importance, camera.scale, 1, repo.glyphSize) + hitSlop
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

export function flowerColor(colorIndex: number): string {
  return FLOWER_PALETTE[colorIndex % FLOWER_PALETTE.length].glyph
}
