import type { MapRepo, Point } from './types'
import { FLOWER_SLOTS } from './flowerScene'
import { layoutFlowerMarks } from './flowerMarks'

/** Label colors paired with the exported flowers in Figma frame 64:20526. */
export const FLOWER_PALETTE = [
  { glyph: '#3991fc', chipBg: '#ebf4ff' },
  { glyph: '#990099', chipBg: '#f6eaff' },
  { glyph: '#76baff', chipBg: '#f0f7ff' },
  { glyph: '#fc5239', chipBg: '#ffefeb' },
  { glyph: '#23aeb0', chipBg: '#eaffff' },
  { glyph: '#310774', chipBg: '#eeebff' },
  { glyph: '#395afc', chipBg: '#eef0ff' },
  { glyph: '#6270ff', chipBg: '#f4f5ff' },
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

export type MapLayoutMode = 'flowers' | 'language' | 'category'
export type FlowerGrouping = 'vulnerabilities' | 'category'

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
 * Place repos into category or vulnerability-bucket flowers.
 * Each node keeps identity; `x`/`y` become flower-layout display coords.
 */
export function layoutFlowerMap(
  repos: MapRepo[],
  preferredIds: ReadonlySet<string> | null = null,
  grouping: FlowerGrouping = 'vulnerabilities',
): {
  repos: MapRepo[]
  flowers: FlowerCluster[]
} {
  if (repos.length === 0) return { repos: [], flowers: [] }

  const groupLabel = (repo: MapRepo) => grouping === 'category'
    ? repo.category?.trim() || 'other'
    : primaryBucket(repo)
  const groups = new Map<string, MapRepo[]>()
  for (const repo of repos) {
    const key = groupLabel(repo)
    const list = groups.get(key)
    if (list) list.push(repo)
    else groups.set(key, [repo])
  }

  // Keep the eight-slot artwork, but bring a searched/selected rare bucket into
  // view instead of silently dropping its matches from the map.
  const keys = [...groups.keys()]
    .sort((a, b) => groups.get(b)!.length - groups.get(a)!.length || a.localeCompare(b))
    .slice(0, FLOWER_SLOTS.length)
  if (preferredIds?.size) {
    const byId = new Map(repos.map((repo) => [repo.id, repo]))
    const required = [...new Set([...preferredIds].flatMap((id) => {
      const repo = byId.get(id)
      return repo ? [groupLabel(repo)] : []
    }))].slice(0, FLOWER_SLOTS.length)
    for (const bucket of required) {
      if (keys.includes(bucket)) continue
      let replacement = -1
      for (let i = keys.length - 1; i >= 0; i--) {
        if (!required.includes(keys[i])) { replacement = i; break }
      }
      if (replacement >= 0) keys[replacement] = bucket
    }
  }
  const flowers: FlowerCluster[] = []
  const positioned: MapRepo[] = []

  keys.forEach((key, index) => {
    const members = groups.get(key)!.slice().sort((a, b) => b.importance - a.importance)
    const slot = FLOWER_SLOTS[index]
    const center = slot.center
    const baseR = slot.bounds.height / 2.55
    const colorIndex = index

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

    const marks = layoutFlowerMarks(members.length, center, slot.bounds.width * 0.75, slot.bounds.height * 0.6)
    members.forEach((repo, i) => {
      const next: MapRepo = {
        ...repo,
        ...marks.points[i],
        glyphSize: marks.glyphSize,
        flowerId: key,
      }
      positioned.push(next)
    })
  })

  return { repos: positioned, flowers }
}

/** Include the exact bloom and its Figma-positioned category label when focusing. */
export function flowerWorldBounds(flower: FlowerCluster) {
  const slot = FLOWER_SLOTS[flower.colorIndex]
  return {
    minX: Math.min(slot.bounds.x, slot.label.x, slot.center.x - slot.label.width / 2),
    maxX: Math.max(slot.bounds.x + slot.bounds.width, slot.label.x + slot.label.width, slot.center.x + slot.label.width / 2),
    minY: slot.bounds.y,
    maxY: Math.max(slot.bounds.y + slot.bounds.height + 77, slot.label.y + 63),
  }
}
