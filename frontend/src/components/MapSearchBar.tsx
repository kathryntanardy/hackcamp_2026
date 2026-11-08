import { useEffect, useId, useRef, useState } from 'react'
import chevronDownIcon from '../assets/icons/chevron-down.svg'
import searchIcon from '../assets/icons/search.svg'
import plusIcon from '../assets/icons/plus.svg'
import minusIcon from '../assets/icons/minus.svg'
import type { RepoListItem } from './RepoListSidebar'

export type MapSearchScope = 'all' | 'vulnerabilities' | 'category' | 'name'

export type MapSearchBarProps = {
  query?: string
  scope?: MapSearchScope
  results?: RepoListItem[]
  loading?: boolean
  error?: string | null
  onQueryChange?: (query: string) => void
  onScopeChange?: (scope: MapSearchScope) => void
  onSelectResult?: (repoId: string) => void
  onZoomIn?: () => void
  onZoomOut?: () => void
}

const SCOPE_OPTIONS: { id: MapSearchScope; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'vulnerabilities', label: 'Vulnerabilities' },
  { id: 'category', label: 'Category' },
  { id: 'name', label: 'Repository' },
]

const MAX_VISIBLE_RESULTS = 8

export function MapSearchBar({
  query = '',
  scope = 'all',
  results = [],
  loading = false,
  error = null,
  onQueryChange,
  onScopeChange,
  onSelectResult,
  onZoomIn,
  onZoomOut,
}: MapSearchBarProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [resultsOpen, setResultsOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const menuId = useId()
  const resultsId = useId()
  const trimmed = query.trim()
  const visibleResults = results.slice(0, MAX_VISIBLE_RESULTS)
  const showResults = resultsOpen && trimmed.length > 0
  const buttonLabel =
    SCOPE_OPTIONS.find((option) => option.id === scope)?.label ?? 'All'

  useEffect(() => {
    if (!menuOpen && !showResults) return
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setMenuOpen(false)
        setResultsOpen(false)
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMenuOpen(false)
        setResultsOpen(false)
      }
    }
    window.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [menuOpen, showResults])

  function selectResult(repoId: string) {
    setResultsOpen(false)
    setMenuOpen(false)
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
            className={`map-search__scope-btn${menuOpen ? ' is-open' : ''}`}
            aria-haspopup="listbox"
            aria-expanded={menuOpen}
            aria-controls={menuId}
            onClick={() => {
              setResultsOpen(false)
              setMenuOpen((open) => !open)
            }}
          >
            <span className="map-search__category-name">{buttonLabel}</span>
            <img
              src={chevronDownIcon}
              alt=""
              width={16}
              height={16}
            />
          </button>

          {menuOpen ? (
            <ul
              className="map-search__menu"
              id={menuId}
              role="listbox"
              aria-label="Search scope"
            >
              {SCOPE_OPTIONS.map((option) => (
                <li key={option.id} role="option" aria-selected={scope === option.id}>
                  <button
                    type="button"
                    className={`map-search__menu-item${scope === option.id ? ' is-active' : ''}`}
                    onClick={() => {
                      onScopeChange?.(option.id)
                      setMenuOpen(false)
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
                setMenuOpen(false)
              }}
            />
            <img src={searchIcon} alt="" width={15} height={15} />
          </label>

          {showResults ? (
            <ul className="map-search__results" id={resultsId} role="listbox" aria-label="Search results">
              {visibleResults.length === 0 && loading ? (
                <li className="map-search__results-empty">Searching…</li>
              ) : visibleResults.length === 0 && error ? (
                <li className="map-search__results-empty is-error" role="alert">
                  {error}
                </li>
              ) : visibleResults.length === 0 ? (
                <li className="map-search__results-empty">No matches for “{trimmed}”.</li>
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
              {loading && visibleResults.length > 0 ? (
                <li className="map-search__results-more">Refining…</li>
              ) : null}
              {error && visibleResults.length > 0 ? (
                <li className="map-search__results-empty is-error" role="alert">
                  {error}
                </li>
              ) : null}
              {!loading && !error && results.length > MAX_VISIBLE_RESULTS ? (
                <li className="map-search__results-more">
                  +{results.length - MAX_VISIBLE_RESULTS} more on the map
                </li>
              ) : null}
            </ul>
          ) : null}
        </div>
      </form>
    </div>
  )
}
