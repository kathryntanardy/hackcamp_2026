import { useEffect, useId, useRef, useState } from 'react'
import chevronDownIcon from '../assets/icons/chevron-down.svg'
import searchIcon from '../assets/icons/search.svg'
import plusIcon from '../assets/icons/plus.svg'
import minusIcon from '../assets/icons/minus.svg'
import type { RepoListItem } from './RepoListSidebar'

export type MapSearchScope = 'all' | 'name' | 'category' | 'language'

export type MapSearchBarProps = {
  query?: string
  scope?: MapSearchScope
  results?: RepoListItem[]
  onQueryChange?: (query: string) => void
  onScopeChange?: (scope: MapSearchScope) => void
  onSelectResult?: (repoId: string) => void
  onZoomIn?: () => void
  onZoomOut?: () => void
}

const SCOPE_OPTIONS: { id: MapSearchScope; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'name', label: 'Name' },
  { id: 'category', label: 'Category' },
  { id: 'language', label: 'Language' },
]

const MAX_VISIBLE_RESULTS = 8

export function MapSearchBar({
  query = '',
  scope = 'all',
  results = [],
  onQueryChange,
  onScopeChange,
  onSelectResult,
  onZoomIn,
  onZoomOut,
}: MapSearchBarProps) {
  const [scopeOpen, setScopeOpen] = useState(false)
  const [resultsOpen, setResultsOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const listId = useId()
  const resultsId = useId()
  const activeLabel = SCOPE_OPTIONS.find((o) => o.id === scope)?.label ?? 'All'
  const trimmed = query.trim()
  const visibleResults = results.slice(0, MAX_VISIBLE_RESULTS)
  const showResults = resultsOpen && trimmed.length > 0

  useEffect(() => {
    if (!scopeOpen && !showResults) return
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setScopeOpen(false)
        setResultsOpen(false)
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setScopeOpen(false)
        setResultsOpen(false)
      }
    }
    window.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [scopeOpen, showResults])

  function selectResult(repoId: string) {
    setResultsOpen(false)
    setScopeOpen(false)
    // Blur so mobile keyboard closes before the detail sheet opens.
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur()
    }
    onSelectResult?.(repoId)
  }

  return (
    <div className="map-toolbar" ref={rootRef}>
      <div className="map-zoom" role="group" aria-label="Map zoom">
        <button type="button" className="map-zoom__btn" aria-label="Zoom in" onClick={onZoomIn}>
          <img src={plusIcon} alt="" width={24} height={24} />
        </button>
        <span className="map-zoom__divider" aria-hidden="true" />
        <button type="button" className="map-zoom__btn" aria-label="Zoom out" onClick={onZoomOut}>
          <img src={minusIcon} alt="" width={24} height={24} />
        </button>
      </div>

      <form
        className="map-search"
        role="search"
        onSubmit={(event) => {
          event.preventDefault()
          if (visibleResults[0]) selectResult(visibleResults[0].id)
        }}
      >
        <div className="map-search__scope">
          <button
            type="button"
            className="map-search__scope-btn"
            aria-haspopup="listbox"
            aria-expanded={scopeOpen}
            aria-controls={listId}
            onClick={() => {
              setResultsOpen(false)
              setScopeOpen((open) => !open)
            }}
          >
            <span>{activeLabel}</span>
            <img src={chevronDownIcon} alt="" width={24} height={24} />
          </button>
          {scopeOpen ? (
            <ul className="map-search__menu" id={listId} role="listbox" aria-label="Search scope">
              {SCOPE_OPTIONS.map((option) => (
                <li key={option.id} role="option" aria-selected={scope === option.id}>
                  <button
                    type="button"
                    className={`map-search__menu-item${scope === option.id ? ' is-active' : ''}`}
                    onClick={() => {
                      onScopeChange?.(option.id)
                      setScopeOpen(false)
                    }}
                  >
                    {option.label}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <div className="map-search__field-wrap">
          <label className="map-search__field">
            <span className="visually-hidden">Search repositories</span>
            <input
              type="search"
              value={query}
              placeholder="Search..."
              autoComplete="off"
              enterKeyHint="search"
              aria-autocomplete="list"
              aria-controls={resultsId}
              aria-expanded={showResults}
              onFocus={() => setResultsOpen(true)}
              onChange={(event) => {
                onQueryChange?.(event.target.value)
                setResultsOpen(true)
                setScopeOpen(false)
              }}
            />
            <img src={searchIcon} alt="" width={15} height={15} />
          </label>

          {showResults ? (
            <ul className="map-search__results" id={resultsId} role="listbox" aria-label="Search results">
              {visibleResults.length === 0 ? (
                <li className="map-search__results-empty">No repositories match “{trimmed}”.</li>
              ) : (
                visibleResults.map((repo) => (
                  <li key={repo.id} role="option">
                    <button
                      type="button"
                      className="map-search__result"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => selectResult(repo.id)}
                    >
                      <span className="map-search__result-name">{repo.name}</span>
                      <span className="map-search__result-meta">
                        {repo.category !== '—' ? repo.category : repo.id}
                      </span>
                    </button>
                  </li>
                ))
              )}
              {results.length > MAX_VISIBLE_RESULTS ? (
                <li className="map-search__results-more">
                  +{results.length - MAX_VISIBLE_RESULTS} more in the sidebar
                </li>
              ) : null}
            </ul>
          ) : null}
        </div>
      </form>
    </div>
  )
}
