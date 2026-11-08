import { StrictMode, useCallback, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { fetchFindings } from './api/findings'
import { mapFindingToListItem } from './api/mapFindingToListItem'
import { mapRepoToListItem } from './api/mapRepoToListItem'
import { mapRepoToMapPoint } from './api/mapRepoToMapPoint'
import { mapRepoToSidebar } from './api/mapRepoToSidebar'
import { fetchRepo, fetchRepos } from './api/repos'
import type { FindingListEntry } from './api/types'
import {
  FindingsView,
  type FindingsRiskFilter,
} from './components/FindingsView'
import { FavouritesSidebar } from './components/FavouritesSidebar'
import { GalaxyMap } from './components/GalaxyMap'
import {
  MapSearchBar,
  type MapSearchScope,
} from './components/MapSearchBar'
import {
  RepoListSidebar,
  type RepoListItem,
} from './components/RepoListSidebar'
import { RepoSidebar, type RepoSidebarProps } from './components/RepoSidebar'
import { SidebarPanel } from './components/SidebarPanel'
import { TopNavbar, type TopNavbarTab } from './components/TopNavbar'
import { useFavourites } from './favourites/useFavourites'
import type { MapRepo } from './map/types'
import { useMapCamera } from './map/useMapCamera'
import './styles.css'

function App() {
  const [repos, setRepos] = useState<RepoListItem[]>([])
  const [mapRepos, setMapRepos] = useState<MapRepo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const mapCamera = useMapCamera()

  const [findings, setFindings] = useState<FindingListEntry[]>([])
  const [findingsError, setFindingsError] = useState<string | null>(null)
  const [findingsLoading, setFindingsLoading] = useState(false)
  const [riskFilter, setRiskFilter] = useState<FindingsRiskFilter>('all')

  const [tab, setTab] = useState<TopNavbarTab>('map')
  const [sidebarWidth, setSidebarWidth] = useState(580)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchScope, setSearchScope] = useState<MapSearchScope>('all')

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<RepoSidebarProps | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [view, setView] = useState<'list' | 'detail'>('list')
  const [listMode, setListMode] = useState<'browse' | 'saved'>('browse')
  const favourites = useFavourites()

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    fetchRepos(controller.signal)
      .then((entries) => {
        setRepos(entries.map(mapRepoToListItem))
        setMapRepos(
          entries
            .map(mapRepoToMapPoint)
            .filter((point): point is MapRepo => point != null),
        )
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const message = err instanceof Error ? err.message : 'Failed to load repos'
        setError(message)
        setLoading(false)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (tab !== 'findings') return
    const controller = new AbortController()
    setFindingsLoading(true)
    setFindingsError(null)
    fetchFindings(
      riskFilter === 'all' ? {} : { risk: riskFilter },
      controller.signal,
    )
      .then((rows) => {
        setFindings(rows)
        setFindingsLoading(false)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const message = err instanceof Error ? err.message : 'Failed to load findings'
        setFindingsError(message)
        setFindingsLoading(false)
      })
    return () => controller.abort()
  }, [tab, riskFilter])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      setDetailError(null)
      setDetailLoading(false)
      setView('list')
      return
    }

    setView('detail')
    const controller = new AbortController()
    setDetailLoading(true)
    setDetailError(null)
    fetchRepo(selectedId, controller.signal)
      .then((repo) => {
        setDetail(mapRepoToSidebar(repo))
        setDetailLoading(false)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const message = err instanceof Error ? err.message : 'Failed to load repo'
        setDetail(null)
        setDetailError(message)
        setDetailLoading(false)
      })
    return () => controller.abort()
  }, [selectedId])

  const findingListItems = useMemo(
    () => findings.map(mapFindingToListItem),
    [findings],
  )

  const filteredRepos = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return repos
    return repos.filter((repo) => {
      const name = repo.name.toLowerCase()
      const category = repo.category.toLowerCase()
      const description = repo.description.toLowerCase()
      if (searchScope === 'name') return name.includes(q)
      if (searchScope === 'category') return category.includes(q)
      if (searchScope === 'language') {
        return description.includes(q) || name.includes(q)
      }
      return name.includes(q) || category.includes(q) || description.includes(q)
    })
  }, [repos, searchQuery, searchScope])

  const { setViewportSize, fitToRepos, pan, zoomIn, zoomOut, zoomByFactor, camera } =
    mapCamera

  useEffect(() => {
    if (mapRepos.length === 0) return
    fitToRepos(mapRepos)
  }, [mapRepos, fitToRepos])

  const handleViewportChange = useCallback(
    (width: number, height: number) => {
      setViewportSize(width, height)
      if (mapRepos.length > 0) fitToRepos(mapRepos)
    },
    [fitToRepos, mapRepos, setViewportSize],
  )

  const backLabel =
    listMode === 'saved'
      ? '← Favourites'
      : tab === 'findings'
        ? '← Findings'
        : '← Repositories'

  function handleBack() {
    setSelectedId(null)
  }

  function handleViewSaved() {
    setSelectedId(null)
    setListMode('saved')
    setView('list')
  }

  function handleSelectRepo(id: string) {
    setSelectedId(id)
  }

  function handleTabChange(next: TopNavbarTab) {
    setTab(next)
    setSelectedId(null)
    setListMode('browse')
  }

  let detailPane = null
  if (selectedId) {
    if (detailLoading) {
      detailPane = (
        <aside className="repo-sidebar repo-sidebar--status" aria-busy="true">
          <p>Loading {selectedId}…</p>
          <button type="button" className="repo-sidebar__back" onClick={handleBack}>
            {backLabel}
          </button>
        </aside>
      )
    } else if (detailError) {
      detailPane = (
        <aside className="repo-sidebar repo-sidebar--status" role="alert">
          <p>Could not load {selectedId}.</p>
          <p className="repo-sidebar__error-detail">{detailError}</p>
          <button type="button" className="repo-sidebar__back" onClick={handleBack}>
            {backLabel}
          </button>
        </aside>
      )
    } else if (detail) {
      detailPane = (
        <RepoSidebar
          {...detail}
          onBack={handleBack}
          backLabel={backLabel}
          onViewSaved={handleViewSaved}
          favouriteLists={favourites.lists}
          isFavourite={favourites.isFavourite(detail.repoId ?? '')}
          favouriteListsForRepo={favourites.listsForRepo(detail.repoId ?? '')}
          onToggleFavourite={favourites.toggleFavourite}
          onToggleInList={favourites.toggleInList}
          onCreateFavouriteList={favourites.createList}
        />
      )
    }
  }

  const listSidebar =
    listMode === 'saved' ? (
      <FavouritesSidebar
        lists={favourites.lists}
        repos={repos}
        selectedId={selectedId}
        onBack={() => setListMode('browse')}
        onSelectRepo={handleSelectRepo}
        onCreateList={favourites.createList}
        onRenameList={favourites.renameList}
        onDeleteList={favourites.deleteList}
        onRemoveFromList={favourites.removeFromList}
      />
    ) : tab === 'findings' ? (
      <RepoListSidebar
        title="Agent Findings"
        metaLabel="Investigation findings"
        scoreLabel="Confidence:"
        categoryLabel="Category:"
        emptyLabel="No headline."
        countLabel={
          findingsLoading
            ? undefined
            : `${findingListItems.length} ${findingListItems.length === 1 ? 'finding' : 'findings'}`
        }
        repos={findingListItems}
        loading={findingsLoading}
        error={findingsError}
        selectedId={selectedId}
        onViewSaved={handleViewSaved}
        onSelectRepo={handleSelectRepo}
      />
    ) : (
      <RepoListSidebar
        repos={filteredRepos}
        loading={loading}
        error={error}
        selectedId={selectedId}
        onViewSaved={handleViewSaved}
        onSelectRepo={handleSelectRepo}
        countLabel={
          searchQuery.trim()
            ? `${filteredRepos.length} of ${repos.length} repositories`
            : undefined
        }
      />
    )

  return (
    <div className="app-shell">
      <div className="app-shell__main">
        <TopNavbar activeTab={tab} onTabChange={handleTabChange} />
        {tab === 'findings' ? (
          <FindingsView
            findings={findings}
            loading={findingsLoading}
            error={findingsError}
            selectedId={selectedId}
            riskFilter={riskFilter}
            onRiskFilterChange={setRiskFilter}
            onSelectFinding={handleSelectRepo}
          />
        ) : (
          <main className="app-shell__map" aria-label="Repository galaxy map">
            <GalaxyMap
              repos={mapRepos}
              camera={camera}
              selectedId={selectedId}
              onSelectRepo={handleSelectRepo}
              onViewportChange={handleViewportChange}
              onPan={pan}
              onZoomByFactor={zoomByFactor}
            />
            <MapSearchBar
              query={searchQuery}
              scope={searchScope}
              results={filteredRepos}
              onQueryChange={setSearchQuery}
              onScopeChange={setSearchScope}
              onSelectResult={handleSelectRepo}
              onZoomIn={() => zoomIn()}
              onZoomOut={() => zoomOut()}
            />
          </main>
        )}
      </div>
      <SidebarPanel width={sidebarWidth} onWidthChange={setSidebarWidth}>
        <div
          className={`sidebar-stack${view === 'detail' ? ' is-detail' : ' is-list'}`}
          aria-live="polite"
        >
          <div className="sidebar-stack__pane sidebar-stack__pane--list">
            {listSidebar}
          </div>
          <div className="sidebar-stack__pane sidebar-stack__pane--detail">
            {detailPane}
          </div>
        </div>
      </SidebarPanel>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
)
