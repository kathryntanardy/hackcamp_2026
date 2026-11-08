import type { MapRepo, Point } from './types'

/** Soft petal fills matching Figma flower palette (40:17144 bloom). */
export const FLOWER_PALETTE = [
  { fill: 'rgba(57, 145, 252, 0.55)', core: 'rgba(57, 145, 252, 0.78)', glyph: '#3991fc', chipBg: '#ebf4ff' },
  { fill: 'rgba(57, 90, 252, 0.5)', core: 'rgba(57, 90, 252, 0.72)', glyph: '#395afc', chipBg: '#eef0ff' },
  { fill: 'rgba(252, 82, 57, 0.5)', core: 'rgba(252, 82, 57, 0.72)', glyph: '#fc5239', chipBg: '#ffeae6' },
  { fill: 'rgba(50, 180, 170, 0.5)', core: 'rgba(20, 140, 130, 0.65)', glyph: '#1f8a82', chipBg: '#e8f8f6' },
  { fill: 'rgba(230, 180, 50, 0.5)', core: 'rgba(190, 140, 20, 0.65)', glyph: '#b08a14', chipBg: '#fff8e6' },
  { fill: 'rgba(120, 90, 190, 0.5)', core: 'rgba(80, 50, 150, 0.65)', glyph: '#5c3d9e', chipBg: '#f2ecff' },
  { fill: 'rgba(90, 100, 120, 0.45)', core: 'rgba(50, 55, 70, 0.6)', glyph: '#4a5160', chipBg: '#f0f1f3' },
] as const

export type VulnSeverity = 'high' | 'medium' | 'low'

/** Severity highlight when hovering High / Med / Low on a flower label. */
export const SEVERITY_HIGHLIGHT = '#fc5239'

/** Glyph fills matching Figma zoomed map (40:17030). */
export const SEVERITY_GLYPH: Record<VulnSeverity | 'none', string> = {
  high: '#fc5239',
  medium: '#e0a21a',
  low: '#2f9e6b',
  none: '#8a8a8a',
}

export type FlowerCluster = {
  id: string
  label: string
  center: Point
  radius: number
  colorIndex: number
  repoIds: string[]
  counts: { high: number; medium: number; low: number }
}

/** Map list filter: whole flower category, or one High/Med/Low band within it. */
export type SeverityFocus = {
  flowerId: string
  tone: VulnSeverity | null
}

const NONE = 'No GitHub advisories'
const OTHER = 'Other / unclassified'

export function primaryBucket(repo: Pick<MapRepo, 'vulnBuckets'>): string {
  const buckets = repo.vulnBuckets.map((b) => b.trim()).filter(Boolean)
  if (buckets.length === 0) return NONE
  // Prefer a concrete CWE bucket over "Other" / "No advisories".
  const concrete = buckets.find((b) => b !== NONE && b !== OTHER)
  if (concrete) return concrete
  if (buckets.includes(OTHER)) return OTHER
  if (buckets.includes(NONE)) return NONE
  return buckets[0] ?? NONE
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

export type MapLayoutMode = 'flowers' | 'language' | 'category'

/**
 * Language / category cluster scatter using gold `x,y` or `cat_x,cat_y`.
 * Nodes keep their warehouse positions; no flower blooms.
 */
export function layoutClusterMap(
  repos: MapRepo[],
  mode: 'language' | 'category',
): {
  repos: MapRepo[]
  flowers: FlowerCluster[]
} {
  if (repos.length === 0) return { repos: [], flowers: [] }
  const positioned = repos.map((repo) => ({
    ...repo,
    x: mode === 'category' ? repo.catX : repo.x,
    y: mode === 'category' ? repo.catY : repo.y,
    flowerId: primaryBucket(repo),
  }))
  return { repos: positioned, flowers: [] }
}

export function layoutMapRepos(
  repos: MapRepo[],
  mode: MapLayoutMode = 'flowers',
): {
  repos: MapRepo[]
  flowers: FlowerCluster[]
} {
  if (mode === 'flowers') return layoutFlowerMap(repos)
  return layoutClusterMap(repos, mode)
}

/**
 * Place repos into vulnerability-bucket flowers.
 * Each node keeps identity; `x`/`y` become flower-layout display coords.
 */
export function layoutFlowerMap(repos: MapRepo[]): {
  repos: MapRepo[]
  flowers: FlowerCluster[]
} {
  if (repos.length === 0) return { repos: [], flowers: [] }

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

    const counts = { high: 0, medium: 0, low: 0 }
    for (const repo of members) {
      if (repo.vulnerabilityTone === 'high') counts.high += 1
      else if (repo.vulnerabilityTone === 'medium') counts.medium += 1
      else if (repo.vulnerabilityTone === 'low') counts.low += 1
    }

    flowers.push({
      id: key,
      label: key,
      center,
      radius: baseR,
      colorIndex,
      repoIds: members.map((m) => m.id),
      counts,
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

  return { repos: positioned, flowers }
}

/**
 * World bounds that frame an entire flower bloom + label.
 * Matches flowerBloom draw size (height ≈ radius·2.55, aspect 1033/771).
 */
export function flowerWorldBounds(flower: FlowerCluster): {
  minX: number
  maxX: number
  minY: number
  maxY: number
} {
  const halfH = flower.radius * 1.35
  const halfW = halfH * (1033 / 771)
  const labelRoom = flower.radius * 0.7
  return {
    minX: flower.center.x - halfW,
    maxX: flower.center.x + halfW,
    minY: flower.center.y - halfH,
    maxY: flower.center.y + halfH + labelRoom,
  }
}
