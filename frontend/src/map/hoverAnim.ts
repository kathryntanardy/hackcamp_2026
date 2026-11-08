import type { MapRepo, Point } from './types'

export const HOVER_GROW = 1.9
export const SELECT_GROW = 1.35

/** Ease-out cubic for size / disperse. */
export function easeOutCubic(t: number): number {
  const x = Math.min(1, Math.max(0, t))
  return 1 - (1 - x) ** 3
}

/**
 * Push neighbours away from the focus node (hover or selection).
 * Strength falls off with world distance; scaled by animated amount 0..1.
 */
export function dispersePoint(
  repo: Pick<MapRepo, 'id' | 'x' | 'y'>,
  focus: Pick<MapRepo, 'id' | 'x' | 'y'> | null,
  amount: number,
): Point {
  if (!focus || amount <= 0 || repo.id === focus.id) {
    return { x: repo.x, y: repo.y }
  }
  const dx = repo.x - focus.x
  const dy = repo.y - focus.y
  const dist = Math.hypot(dx, dy) || 0.0001
  // Soft falloff — nearby x's move more, far ones barely twitch.
  const influence = Math.exp(-dist / 34)
  const push = 20 * easeOutCubic(amount) * influence
  return {
    x: repo.x + (dx / dist) * push,
    y: repo.y + (dy / dist) * push,
  }
}

export function growFactor(
  isHovered: boolean,
  isSelected: boolean,
  hoverAmount: number,
): number {
  if (isHovered) return 1 + (HOVER_GROW - 1) * easeOutCubic(hoverAmount)
  if (isSelected) return SELECT_GROW
  return 1
}
