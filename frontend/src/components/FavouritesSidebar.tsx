import { useMemo, useState } from 'react'
import savedBookmarkIcon from '../assets/icons/saved-bookmark.svg'
import cornerDownRightIcon from '../assets/icons/corner-down-right.svg'
import type { FavouriteList } from '../favourites/types'
import type { RepoListItem } from './RepoListSidebar'

export type FavouritesSidebarProps = {
  lists: FavouriteList[]
  repos: RepoListItem[]
  selectedId?: string | null
  onSelectRepo: (id: string) => void
  onCreateList: (name: string) => string
  onRenameList: (listId: string, name: string) => void
  onDeleteList: (listId: string) => void
  onRemoveFromList: (listId: string, repoId: string) => void
}

export function FavouritesSidebar({
  lists,
  repos,
  selectedId = null,
  onSelectRepo,
  onCreateList,
  onRenameList,
  onDeleteList,
  onRemoveFromList,
}: FavouritesSidebarProps) {
  const [activeListId, setActiveListId] = useState(lists[0]?.id ?? '')
  const [newListName, setNewListName] = useState('')
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')

  const activeList = lists.find((list) => list.id === activeListId) ?? lists[0] ?? null

  const repoById = useMemo(() => {
    const map = new Map<string, RepoListItem>()
    for (const repo of repos) map.set(repo.id, repo)
    return map
  }, [repos])

  const entries = useMemo(() => {
    if (!activeList) return []
    return activeList.repoIds.map((id) => {
      const known = repoById.get(id)
      return (
        known ?? {
          id,
          name: id,
          description: 'Not in the current corpus load.',
          vulnerabilityLabel: 'Unknown',
          vulnerabilityTone: 'none' as const,
          vulnerabilityScore: '—',
          category: '—',
        }
      )
    })
  }, [activeList, repoById])

  const totalSaved = useMemo(() => {
    const ids = new Set<string>()
    for (const list of lists) {
      for (const id of list.repoIds) ids.add(id)
    }
    return ids.size
  }, [lists])

  function submitCreate() {
    const name = newListName.trim()
    if (!name) return
    const id = onCreateList(name)
    setNewListName('')
    setActiveListId(id)
  }

  function startRename(list: FavouriteList) {
    setRenamingId(list.id)
    setRenameValue(list.name)
  }

  function commitRename() {
    if (!renamingId) return
    onRenameList(renamingId, renameValue)
    setRenamingId(null)
    setRenameValue('')
  }

  return (
    <aside className="favourites-sidebar" aria-label="Saved repositories">
      <header className="favourites-sidebar__top">
        <div className="favourites-sidebar__meta">
          <img src={savedBookmarkIcon} alt="" width={17} height={17} />
          <span>Saved repositories</span>
        </div>
      </header>

      <div className="favourites-sidebar__hero">
        <h1 className="favourites-sidebar__title">Saved</h1>
        <p className="favourites-sidebar__subtitle">
          {totalSaved} {totalSaved === 1 ? 'repository' : 'repositories'} across {lists.length}{' '}
          {lists.length === 1 ? 'list' : 'lists'} · stored on this browser
        </p>
      </div>

      <div className="favourites-sidebar__body">
        <section className="favourites-sidebar__lists" aria-label="Favourite lists">
          <ul className="favourites-list-picker">
            {lists.map((list) => {
              const selected = activeList?.id === list.id
              return (
                <li key={list.id}>
                  {renamingId === list.id ? (
                    <form
                      className="favourites-list-picker__rename"
                      onSubmit={(event) => {
                        event.preventDefault()
                        commitRename()
                      }}
                    >
                      <input
                        autoFocus
                        value={renameValue}
                        aria-label="List name"
                        onChange={(event) => setRenameValue(event.target.value)}
                        onBlur={commitRename}
                      />
                    </form>
                  ) : (
                    <button
                      type="button"
                      className={`favourites-list-picker__item${selected ? ' is-selected' : ''}`}
                      onClick={() => setActiveListId(list.id)}
                    >
                      <span className="favourites-list-picker__name">{list.name}</span>
                      <span className="favourites-list-picker__count">{list.repoIds.length}</span>
                    </button>
                  )}
                  <div className="favourites-list-picker__actions">
                    <button type="button" onClick={() => startRename(list)}>
                      Rename
                    </button>
                    <button
                      type="button"
                      disabled={lists.length <= 1}
                      onClick={() => {
                        if (lists.length <= 1) return
                        onDeleteList(list.id)
                        if (activeListId === list.id) {
                          const next = lists.find((row) => row.id !== list.id)
                          if (next) setActiveListId(next.id)
                        }
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>

          <div className="favourites-sidebar__create">
            <input
              type="text"
              value={newListName}
              placeholder="New list name"
              aria-label="New favourite list name"
              onChange={(event) => setNewListName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  submitCreate()
                }
              }}
            />
            <button type="button" onClick={submitCreate} disabled={!newListName.trim()}>
              Create list
            </button>
          </div>
        </section>

        <section className="favourites-sidebar__repos" aria-label={activeList?.name ?? 'List'}>
          <p className="favourites-sidebar__count">
            {activeList
              ? `${entries.length} in “${activeList.name}”`
              : 'No lists yet'}
          </p>
          {entries.length === 0 ? (
            <p className="favourites-sidebar__empty">
              Save a repository to add it here. Right-click the bookmark to choose a list.
            </p>
          ) : (
            <ul className="repo-list">
              {entries.map((repo) => (
                <li key={repo.id}>
                  <div
                    className={`repo-card favourites-repo-card${
                      selectedId === repo.id ? ' is-selected' : ''
                    }`}
                  >
                    <button
                      type="button"
                      className="favourites-repo-card__open"
                      aria-current={selectedId === repo.id ? 'true' : undefined}
                      onClick={() => onSelectRepo(repo.id)}
                    >
                      <div className="repo-card__main">
                        <div className="repo-card__copy">
                          <p className="repo-card__name">{repo.name}</p>
                          <div className="repo-card__desc-row">
                            <img src={cornerDownRightIcon} alt="" width={16} height={16} />
                            <p className="repo-card__desc">
                              {repo.description || 'No overview available.'}
                            </p>
                          </div>
                        </div>
                      </div>
                      <div className="repo-card__footer">
                        <p className="repo-card__metric">
                          <span className="repo-card__metric-label">Category:</span>{' '}
                          <span className="repo-card__metric-value">{repo.category}</span>
                        </p>
                      </div>
                    </button>
                    {activeList ? (
                      <button
                        type="button"
                        className="favourites-repo-card__remove"
                        aria-label={`Remove ${repo.name} from ${activeList.name}`}
                        onClick={() => onRemoveFromList(activeList.id, repo.id)}
                      >
                        Remove
                      </button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </aside>
  )
}
