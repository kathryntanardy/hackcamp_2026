import { useCallback, useEffect, useMemo, useState } from 'react'
import { loadFavourites, saveFavourites } from './storage'
import {
  DEFAULT_LIST_ID,
  DEFAULT_LIST_NAME,
  type FavouriteList,
  type FavouritesState,
} from './types'

function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `list-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function useFavourites() {
  const [state, setState] = useState<FavouritesState>(() => loadFavourites())

  useEffect(() => {
    saveFavourites(state)
  }, [state])

  const favouriteIds = useMemo(() => {
    const ids = new Set<string>()
    for (const list of state.lists) {
      for (const id of list.repoIds) ids.add(id)
    }
    return ids
  }, [state.lists])

  const isFavourite = useCallback(
    (repoId: string) => favouriteIds.has(repoId),
    [favouriteIds],
  )

  const listsForRepo = useCallback(
    (repoId: string) => state.lists.filter((list) => list.repoIds.includes(repoId)),
    [state.lists],
  )

  const createList = useCallback((name: string) => {
    const trimmed = name.trim() || 'Untitled list'
    const list: FavouriteList = {
      id: newId(),
      name: trimmed,
      repoIds: [],
      createdAt: Date.now(),
    }
    setState((prev) => ({ lists: [...prev.lists, list] }))
    return list.id
  }, [])

  const renameList = useCallback((listId: string, name: string) => {
    const trimmed = name.trim()
    if (!trimmed) return
    setState((prev) => ({
      lists: prev.lists.map((list) =>
        list.id === listId ? { ...list, name: trimmed } : list,
      ),
    }))
  }, [])

  const deleteList = useCallback((listId: string) => {
    setState((prev) => {
      if (prev.lists.length <= 1) return prev
      const remaining = prev.lists.filter((list) => list.id !== listId)
      if (remaining.length === 0) {
        return {
          lists: [
            {
              id: DEFAULT_LIST_ID,
              name: DEFAULT_LIST_NAME,
              repoIds: [],
              createdAt: Date.now(),
            },
          ],
        }
      }
      return { lists: remaining }
    })
  }, [])

  const addToList = useCallback((listId: string, repoId: string) => {
    setState((prev) => ({
      lists: prev.lists.map((list) => {
        if (list.id !== listId || list.repoIds.includes(repoId)) return list
        return { ...list, repoIds: [...list.repoIds, repoId] }
      }),
    }))
  }, [])

  const removeFromList = useCallback((listId: string, repoId: string) => {
    setState((prev) => ({
      lists: prev.lists.map((list) => {
        if (list.id !== listId) return list
        return { ...list, repoIds: list.repoIds.filter((id) => id !== repoId) }
      }),
    }))
  }, [])

  const toggleInList = useCallback((listId: string, repoId: string) => {
    setState((prev) => ({
      lists: prev.lists.map((list) => {
        if (list.id !== listId) return list
        if (list.repoIds.includes(repoId)) {
          return { ...list, repoIds: list.repoIds.filter((id) => id !== repoId) }
        }
        return { ...list, repoIds: [...list.repoIds, repoId] }
      }),
    }))
  }, [])

  /** Quick-star: add to first list, or remove from every list. */
  const toggleFavourite = useCallback((repoId: string) => {
    setState((prev) => {
      const inAny = prev.lists.some((list) => list.repoIds.includes(repoId))
      if (inAny) {
        return {
          lists: prev.lists.map((list) => ({
            ...list,
            repoIds: list.repoIds.filter((id) => id !== repoId),
          })),
        }
      }
      const targetId = prev.lists[0]?.id
      if (!targetId) return prev
      return {
        lists: prev.lists.map((list) =>
          list.id === targetId
            ? { ...list, repoIds: [...list.repoIds, repoId] }
            : list,
        ),
      }
    })
  }, [])

  return {
    lists: state.lists,
    favouriteIds,
    isFavourite,
    listsForRepo,
    createList,
    renameList,
    deleteList,
    addToList,
    removeFromList,
    toggleInList,
    toggleFavourite,
  }
}

export type FavouritesApi = ReturnType<typeof useFavourites>
