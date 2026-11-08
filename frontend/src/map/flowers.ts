import type { MapRepo, Point } from './types'

/** Soft petal fills matching Figma flower palette (40:6204). */
export const FLOWER_PALETTE = [
  { fill: 'rgba(252, 120, 70, 0.55)', core: 'rgba(220, 70, 40, 0.7)', label: '#c4452a' },
  { fill: 'rgba(70, 130, 210, 0.5)', core: 'rgba(40, 90, 180, 0.65)', label: '#2f5fad' },
  { fill: 'rgba(50, 180, 170, 0.5)', core: 'rgba(20, 140, 130, 0.65)', label: '#1f8a82' },
  { fill: 'rgba(210, 70, 90, 0.5)', core: 'rgba(170, 30, 55, 0.65)', label: '#b02844' },
  { fill: 'rgba(230, 180, 50, 0.5)', core: 'rgba(190, 140, 20, 0.65)', label: '#b08a14' },
  { fill: 'rgba(120, 90, 190, 0.5)', core: 'rgba(80, 50, 150, 0.65)', label: '#5c3d9e' },
  { fill: 'rgba(90, 100, 120, 0.45)', core: 'rgba(50, 55, 70, 0.6)', label: '#4a5160' },
] as const

export type FlowerCluster = {
  id: string
  label: string
  center: Point
  radius: number
  colorIndex: number
  repoIds: string[]
}

export type VulnEdge = {
  a: string
  b: string
  bucket: string
}

const NONE = 'No GitHub advisories'
const OTHER = 'Other / unclassified'

export function primaryBucket(repo: Pick<MapRepo, 'vulnBuckets'>): string {
  const buckets = repo.vulnBuckets.filter(Boolean)
  if (buckets.length === 0) return NONE
  const meaningful = buckets.find((b) => b !== NONE)
  return meaningful ?? buckets[0] ?? NONE
}

function hashSeed(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

/** Petal-modulated radius for a polar angle (ASCII flower silhouette). */
function petalRadius(theta: number, petals: number, base: number): number {
  const wave = Math.abs(Math.cos((petals * theta) / 2))
  return base * (0.38 + 0.62 * Math.pow(wave, 0.85))
}

/**
 * Place repos into vulnerability-bucket flowers.
 * Each node keeps identity; `x`/`y` become flower-layout display coords.
 */
export function layoutFlowerMap(repos: MapRepo[]): {
  repos: MapRepo[]
  flowers: FlowerCluster[]
  edges: VulnEdge[]
} {
  if (repos.length === 0) return { repos: [], flowers: [], edges: [] }

  const groups = new Map<string, MapRepo[]>()
  for (const repo of repos) {
    const key = primaryBucket(repo)
    const list = groups.get(key)
    if (list) list.push(repo)
    else groups.set(key, [repo])
  }

  // Prefer real vuln types first; "none" last.
  const keys = [...groups.keys()].sort((a, b) => {
    if (a === NONE && b !== NONE) return 1
    if (b === NONE && a !== NONE) return -1
    if (a === OTHER && b !== OTHER) return 1
    if (b === OTHER && a !== OTHER) return -1
    return groups.get(b)!.length - groups.get(a)!.length || a.localeCompare(b)
  })

  const flowerCount = keys.length
  // Spread flowers across a wide grid so fit-to-view uses the full canvas.
  const cols = Math.max(1, Math.ceil(Math.sqrt(flowerCount * 1.35)))
  const rows = Math.max(1, Math.ceil(flowerCount / cols))
  const radii = keys.map((key) => {
    const n = groups.get(key)!.length
    return 22 + Math.min(48, Math.sqrt(n) * 4.6)
  })
  const maxR = Math.max(...radii, 28)
  const cell = maxR * 2.65 + 36
  const gridW = (cols - 1) * cell
  const gridH = (rows - 1) * cell
  const flowers: FlowerCluster[] = []
  const positioned: MapRepo[] = []
  const byId = new Map<string, MapRepo>()

  keys.forEach((key, index) => {
    const members = groups.get(key)!.slice().sort((a, b) => b.importance - a.importance)
    const col = index % cols
    const row = Math.floor(index / cols)
    // Stagger odd rows slightly so the field feels less rigid.
    const stagger = row % 2 === 1 ? cell * 0.38 : 0
    const center = {
      x: col * cell + stagger - gridW / 2,
      y: row * cell - gridH / 2,
    }
    const n = members.length
    const petals = n < 12 ? 5 : n < 40 ? 6 : 7
    const baseR = radii[index]
    const colorIndex = index % FLOWER_PALETTE.length

    flowers.push({
      id: key,
      label: key,
      center,
      radius: baseR,
      colorIndex,
      repoIds: members.map((m) => m.id),
    })

    members.forEach((repo, i) => {
      const seed = hashSeed(repo.id)
      // Spiral fill of the flower silhouette so every repo is an "x" cell.
      const t = (i + 0.5) / Math.max(1, n)
      const theta = ((seed % 1000) / 1000) * Math.PI * 2 + i * 2.399963
      const maxPetal = petalRadius(theta, petals, baseR)
      // Leave breathing room between glyphs inside the bloom.
      const r = maxPetal * Math.sqrt(t) * (0.78 + ((seed >> 8) % 100) / 450)
      const jitter = ((seed >> 16) % 100) / 100
      const jt = theta + (jitter - 0.5) * 0.14
      const next: MapRepo = {
        ...repo,
        x: center.x + Math.cos(jt) * r,
        y: center.y + Math.sin(jt) * r,
        flowerId: key,
      }
      positioned.push(next)
      byId.set(next.id, next)
    })
  })

  return { repos: positioned, flowers, edges: buildVulnEdges(positioned) }
}

/** Connect repos that share a vulnerability bucket via nearest-neighbour chains. */
function buildVulnEdges(repos: MapRepo[]): VulnEdge[] {
  const byBucket = new Map<string, MapRepo[]>()
  for (const repo of repos) {
    const buckets = repo.vulnBuckets.length > 0 ? repo.vulnBuckets : [NONE]
    for (const bucket of buckets) {
      if (!bucket || bucket === NONE) continue
      const list = byBucket.get(bucket)
      if (list) list.push(repo)
      else byBucket.set(bucket, [repo])
    }
  }

  const seen = new Set<string>()
  const edges: VulnEdge[] = []

  for (const [bucket, members] of byBucket) {
    if (members.length < 2) continue
    // Cap fan-out: each node links to up to 2 nearest co-bucket neighbours.
    for (const a of members) {
      const nearest = members
        .filter((b) => b.id !== a.id)
        .map((b) => ({
          b,
          d: (a.x - b.x) ** 2 + (a.y - b.y) ** 2,
        }))
        .sort((u, v) => u.d - v.d)
        .slice(0, 2)

      for (const { b } of nearest) {
        const key = a.id < b.id ? `${a.id}|${b.id}|${bucket}` : `${b.id}|${a.id}|${bucket}`
        if (seen.has(key)) continue
        seen.add(key)
        edges.push({ a: a.id, b: b.id, bucket })
      }
    }
  }

  return edges
}

export function drawFlowerPetals(
  ctx: CanvasRenderingContext2D,
  center: Point,
  radius: number,
  colorIndex: number,
  scale: number,
): void {
  const palette = FLOWER_PALETTE[colorIndex % FLOWER_PALETTE.length]
  const petals = 7
  const screenR = radius * scale

  ctx.save()
  for (let i = 0; i < petals; i++) {
    const angle = (i / petals) * Math.PI * 2
    const px = center.x + Math.cos(angle) * screenR * 0.35
    const py = center.y + Math.sin(angle) * screenR * 0.35
    const grad = ctx.createRadialGradient(px, py, screenR * 0.05, px, py, screenR * 0.85)
    grad.addColorStop(0, palette.core)
    grad.addColorStop(0.55, palette.fill)
    grad.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.beginPath()
    ctx.ellipse(
      px,
      py,
      screenR * 0.72,
      screenR * 0.48,
      angle,
      0,
      Math.PI * 2,
    )
    ctx.fillStyle = grad
    ctx.fill()
  }

  // Soft core bloom.
  const core = ctx.createRadialGradient(center.x, center.y, 0, center.x, center.y, screenR * 0.45)
  core.addColorStop(0, palette.core)
  core.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.beginPath()
  ctx.arc(center.x, center.y, screenR * 0.45, 0, Math.PI * 2)
  ctx.fillStyle = core
  ctx.fill()
  ctx.restore()
}

export function drawFlowerLabel(
  ctx: CanvasRenderingContext2D,
  center: Point,
  radius: number,
  label: string,
  colorIndex: number,
  scale: number,
): void {
  const palette = FLOWER_PALETTE[colorIndex % FLOWER_PALETTE.length]
  const x = center.x
  const y = center.y + radius * scale + Math.max(22, scale * 1.2)
  const padX = 10
  const fontPx = Math.round(Math.min(16, Math.max(11, 10 + scale * 0.15)))
  ctx.font = `500 ${fontPx}px "Inter Tight", system-ui, sans-serif`
  const textW = ctx.measureText(label).width
  const boxW = textW + 28 + padX * 2
  const boxH = fontPx + 14
  const left = x - boxW / 2
  const swatch = Math.max(12, fontPx)

  ctx.fillStyle = 'rgba(255,255,255,0.94)'
  ctx.strokeStyle = 'rgba(231,229,230,1)'
  ctx.lineWidth = 1
  roundRect(ctx, left, y - boxH / 2, boxW, boxH, 4)
  ctx.fill()
  ctx.stroke()

  ctx.fillStyle = palette.label
  ctx.fillRect(left + padX, y - swatch / 2, swatch, swatch)

  ctx.fillStyle = '#1e1e1e'
  ctx.textBaseline = 'middle'
  ctx.fillText(label, left + padX + swatch + 8, y)
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}
