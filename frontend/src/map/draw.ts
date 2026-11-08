import { worldToScreen } from './camera'
import {
  FLOWER_PALETTE,
  drawFlowerLabel,
  drawFlowerPetals,
  type FlowerCluster,
  type VulnEdge,
} from './flowers'
import { dispersePoint, growFactor } from './hoverAnim'
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

/** World-space glyph size — screen px = this × camera.scale × grow. */
export function worldGlyphSize(importance: number): number {
  return 2.6 + Math.min(3.4, Math.max(0, importance) * 0.7)
}

export function xFontSize(importance: number, scale: number, grow = 1): number {
  const px = worldGlyphSize(importance) * scale * grow
  return Math.round(Math.min(110, Math.max(14, px)))
}

export function pointRadius(importance: number, scale: number, grow = 1): number {
  return xFontSize(importance, scale, grow) * 0.55
}

export function drawMap(
  ctx: CanvasRenderingContext2D,
  repos: MapRepo[],
  flowers: FlowerCluster[],
  edges: VulnEdge[],
  camera: MapCamera,
  selectedId: string | null,
  hoveredId: string | null,
  hoverAmount: number,
  width: number,
  height: number,
): void {
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = '#fafafa'
  ctx.fillRect(0, 0, width, height)

  const hoverRepo = hoveredId ? repos.find((r) => r.id === hoveredId) ?? null : null
  const amount = hoverRepo ? hoverAmount : 0

  const placed = new Map<string, { x: number; y: number }>()
  for (const repo of repos) {
    placed.set(repo.id, dispersePoint(repo, hoverRepo, amount))
  }

  for (const flower of flowers) {
    const center = worldToScreen(flower.center, camera)
    drawFlowerPetals(ctx, center, flower.radius, flower.colorIndex, camera.scale)
  }

  ctx.save()
  ctx.lineWidth = Math.max(1, camera.scale * 0.04)
  for (const edge of edges) {
    const a = placed.get(edge.a)
    const b = placed.get(edge.b)
    if (!a || !b) continue
    const sa = worldToScreen(a, camera)
    const sb = worldToScreen(b, camera)
    if (
      (sa.x < -80 && sb.x < -80) ||
      (sa.y < -80 && sb.y < -80) ||
      (sa.x > width + 80 && sb.x > width + 80) ||
      (sa.y > height + 80 && sb.y > height + 80)
    ) {
      continue
    }
    const highlight =
      edge.a === selectedId ||
      edge.b === selectedId ||
      edge.a === hoveredId ||
      edge.b === hoveredId
    ctx.strokeStyle = highlight
      ? `rgba(252, 82, 57, ${0.28 + 0.35 * amount})`
      : 'rgba(30, 30, 30, 0.14)'
    ctx.beginPath()
    ctx.moveTo(sa.x, sa.y)
    ctx.lineTo(sb.x, sb.y)
    ctx.stroke()
  }
  ctx.restore()

  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'

  const ordered = [...repos].sort((a, b) => {
    const rank = (id: string) =>
      id === hoveredId ? 2 : id === selectedId ? 1 : 0
    return rank(a.id) - rank(b.id)
  })

  for (const repo of ordered) {
    const world = placed.get(repo.id)!
    const screen = worldToScreen(world, camera)
    const isSelected = repo.id === selectedId
    const isHovered = repo.id === hoveredId
    const grow = growFactor(isHovered, isSelected, amount)
    const size = xFontSize(repo.importance, camera.scale, grow)
    const pad = size

    if (
      screen.x < -pad ||
      screen.y < -pad ||
      screen.x > width + pad ||
      screen.y > height + pad
    ) {
      continue
    }

    ctx.font = `${isHovered || isSelected ? 800 : 700} ${size}px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`

    // Selected only — no hover background / fill ring.
    if (isSelected && !isHovered) {
      ctx.beginPath()
      ctx.arc(screen.x, screen.y, size * 0.62, 0, Math.PI * 2)
      ctx.strokeStyle = '#fc5239'
      ctx.lineWidth = Math.max(1.5, camera.scale * 0.06)
      ctx.stroke()
    }

    if (repo.investigatedInLatestRun && !isHovered) {
      ctx.beginPath()
      ctx.arc(screen.x, screen.y, size * 0.55, 0, Math.PI * 2)
      ctx.strokeStyle = 'rgba(252, 82, 57, 0.4)'
      ctx.lineWidth = 1
      ctx.stroke()
    }

    ctx.fillStyle = statusColor(repo.status)
    ctx.fillText('x', screen.x, screen.y + size * 0.04)
  }

  for (const flower of flowers) {
    const center = worldToScreen(flower.center, camera)
    drawFlowerLabel(
      ctx,
      center,
      flower.radius,
      flower.label,
      flower.colorIndex,
      camera.scale,
    )
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
    const radius = pointRadius(repo.importance, camera.scale, 1) + hitSlop
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
  return FLOWER_PALETTE[colorIndex % FLOWER_PALETTE.length].label
}
