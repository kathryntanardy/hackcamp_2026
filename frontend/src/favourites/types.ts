export type FavouriteList = {
  id: string
  name: string
  repoIds: string[]
  createdAt: number
}

export type FavouritesState = {
  lists: FavouriteList[]
}

export const DEFAULT_LIST_ID = 'default'
export const DEFAULT_LIST_NAME = 'Saved'
export const STORAGE_KEY = 'oci.favourites.v1'

export function createDefaultState(): FavouritesState {
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
