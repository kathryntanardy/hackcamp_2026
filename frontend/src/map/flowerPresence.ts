import type { FlowerCluster } from './flowers'
import type { MapRepo } from './types'

export const FLOWER_FADE_MS = 360

export type FlowerPresence = {
  key: string
  flower: FlowerCluster
  repos: MapRepo[]
  opacity: number
  from: number
  target: number
  startedAt: number
}

function opacityAt(entry: FlowerPresence, now: number): number {
  const t = Math.max(0, Math.min(1, (now - entry.startedAt) / FLOWER_FADE_MS))
  const eased = t * t * (3 - 2 * t)
  return entry.from + (entry.target - entry.from) * eased
}

/** Keep outgoing flowers alive until their bloom, marks, label and branch fade out. */
export function reconcileFlowerPresence(
  previous: FlowerPresence[], repos: MapRepo[], flowers: FlowerCluster[], now: number,
  immediate = false,
): FlowerPresence[] {
  const pending = new Map(previous.map((entry) => [entry.key, entry]))
  const next = flowers.map((flower): FlowerPresence => {
    const key = `${flower.colorIndex}:${flower.id}`
    const old = pending.get(key)
    pending.delete(key)
    const opacity = immediate ? 1 : old ? opacityAt(old, now) : 0
    return {
      key, flower, repos: repos.filter((repo) => repo.flowerId === flower.id),
      opacity, from: old?.target === 1 ? old.from : opacity, target: 1,
      startedAt: old?.target === 1 ? old.startedAt : now,
    }
  })
  if (!immediate) {
    for (const entry of pending.values()) {
      const opacity = opacityAt(entry, now)
      if (opacity === 0) continue
      next.push(entry.target === 0 ? { ...entry, opacity } : {
        ...entry, opacity, from: opacity, target: 0, startedAt: now,
      })
    }
  }
  return next
}

export function advanceFlowerPresence(entries: FlowerPresence[], now: number): FlowerPresence[] {
  return entries.map((entry) => ({ ...entry, opacity: opacityAt(entry, now) }))
    .filter((entry) => entry.target !== 0 || entry.opacity > 0)
}

// First nine entries follow the exported layers. The final entry is the lower
// central trunk, shared by magenta and the upper flower above their junction.
export const CENTRAL_BRANCH_JUNCTION_Y = 705
export const BRANCH_FLOWER_SLOTS = [[1], [2], [0], [4], [7], [5, 6], [3], [3], [7], [1, 7]] as const

/** Relabeling a populated slot must not fade its unchanged artwork twice. */
export function flowerSlotOpacities(entries: Pick<FlowerPresence, 'flower' | 'opacity'>[]): Map<number, number> {
  const slots = new Map<number, number>()
  for (const entry of entries) {
    const slot = entry.flower.colorIndex
    slots.set(slot, Math.min(1, (slots.get(slot) ?? 0) + entry.opacity))
  }
  return slots
}

export function branchOpacities(entries: Pick<FlowerPresence, 'flower' | 'opacity'>[]): number[] {
  const opacityBySlot = flowerSlotOpacities(entries)
  return BRANCH_FLOWER_SLOTS.map((slots) => Math.max(0,
    ...slots.map((slot) => opacityBySlot.get(slot) ?? 0)))
}
