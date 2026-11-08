import {
  createDefaultState,
  STORAGE_KEY,
  type FavouriteList,
  type FavouritesState,
} from './types'

function isList(value: unknown): value is FavouriteList {
  if (!value || typeof value !== 'object') return false
  const row = value as Record<string, unknown>
  return (
    typeof row.id === 'string' &&
    typeof row.name === 'string' &&
    typeof row.createdAt === 'number' &&
    Array.isArray(row.repoIds) &&
    row.repoIds.every((id) => typeof id === 'string')
  )
}

function normalize(raw: unknown): FavouritesState {
  if (!raw || typeof raw !== 'object') return createDefaultState()
  const lists = (raw as { lists?: unknown }).lists
  if (!Array.isArray(lists) || lists.length === 0) return createDefaultState()
  const cleaned = lists.filter(isList).map((list) => ({
    ...list,
    name: list.name.trim() || 'Untitled',
    repoIds: [...new Set(list.repoIds)],
  }))
  return cleaned.length > 0 ? { lists: cleaned } : createDefaultState()
}

export function loadFavourites(): FavouritesState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return createDefaultState()
    return normalize(JSON.parse(raw))
  } catch {
    return createDefaultState()
  }
}

export function saveFavourites(state: FavouritesState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Quota / private mode — keep in-memory state only.
  }
}
