import { useEffect, useId, useRef, useState } from 'react'
import starFilledIcon from '../assets/icons/star-filled.svg'
import starOutlineIcon from '../assets/icons/star-outline.svg'
import type { FavouriteList } from '../favourites/types'

export type FavouriteStarButtonProps = {
  repoId: string
  saved: boolean
  lists: FavouriteList[]
  listsForRepo: FavouriteList[]
  onToggleFavourite: (repoId: string) => void
  onToggleInList: (listId: string, repoId: string) => void
  onCreateList: (name: string) => string
}

export function FavouriteStarButton({
  repoId,
  saved,
  lists,
  listsForRepo,
  onToggleFavourite,
  onToggleInList,
  onCreateList,
}: FavouriteStarButtonProps) {
  const [open, setOpen] = useState(false)
  const [newListName, setNewListName] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const menuId = useId()
  const memberIds = new Set(listsForRepo.map((list) => list.id))

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  function submitNewList() {
    const name = newListName.trim()
    if (!name) return
    const listId = onCreateList(name)
    onToggleInList(listId, repoId)
    setNewListName('')
  }

  return (
    <div className="favourite-star" ref={rootRef}>
      <button
        type="button"
        className={`repo-sidebar__star-btn${saved ? ' is-saved' : ''}`}
        aria-label={saved ? 'Manage favourites' : 'Add to favourites'}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => {
          // One list: quick star/unstar. Multiple lists / right-click: choose lists.
          if (lists.length <= 1) {
            onToggleFavourite(repoId)
            return
          }
          setOpen((value) => !value)
        }}
        onContextMenu={(event) => {
          event.preventDefault()
          setOpen(true)
        }}
      >
        <img
          src={saved ? starOutlineIcon : starFilledIcon}
          alt=""
          width={15}
          height={14}
        />
      </button>
      {open ? (
        <div className="favourite-star__menu" id={menuId} role="dialog" aria-label="Favourite lists">
          <p className="favourite-star__heading">Add to list</p>
          <ul className="favourite-star__lists">
            {lists.map((list) => {
              const checked = memberIds.has(list.id)
              return (
                <li key={list.id}>
                  <label className="favourite-star__row">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggleInList(list.id, repoId)}
                    />
                    <span>{list.name}</span>
                    <span className="favourite-star__count">{list.repoIds.length}</span>
                  </label>
                </li>
              )
            })}
          </ul>
          <div className="favourite-star__create">
            <input
              type="text"
              value={newListName}
              placeholder="New list name"
              aria-label="New list name"
              onChange={(event) => setNewListName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  submitNewList()
                }
              }}
            />
            <button type="button" onClick={submitNewList} disabled={!newListName.trim()}>
              Add
            </button>
          </div>
          {saved ? (
            <button
              type="button"
              className="favourite-star__clear"
              onClick={() => {
                onToggleFavourite(repoId)
                setOpen(false)
              }}
            >
              Remove from all lists
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
