import { StrictMode, useCallback, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { fetchFindings } from './api/findings'
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
import { RepoSidebarSkeleton } from './components/RepoSidebarSkeleton'
import { SidebarPanel } from './components/SidebarPanel'
import { TopNavbar, type TopNavbarTab } from './components/TopNavbar'
import { useFavourites } from './favourites/useFavourites'
import {
  flowerWorldBounds,
  layoutFlowerMap,
  type SeverityFocus,
} from './map/flowers'
import type { MapRepo } from './map/types'
import { useMapCamera } from './map/useMapCamera'
import './styles.css'

const FINDINGS_PAGE_SIZE = 50

function App() {
  const [repos, setRepos] = useState<RepoListItem[]>([])
  const [rawMapRepos, setRawMapRepos] = useState<MapRepo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const mapCamera = useMapCamera()

  const [findings, setFindings] = useState<FindingListEntry[]>([])
  const [findingsTotal, setFindingsTotal] = useState(0)
  const [findingsPage, setFindingsPage] = useState(1)
  const [findingsError, setFindingsError] = useState<string | null>(null)
  const [findingsLoading, setFindingsLoading] = useState(false)
  const [riskFilter, setRiskFilter] = useState<FindingsRiskFilter>('all')

  const [tab, setTab] = useState<TopNavbarTab>('map')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(580)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchScope, setSearchScope] = useState<MapSearchScope>('all')

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<RepoSidebarProps | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [view, setView] = useState<'list' | 'detail'>('list')
  const [listMode, setListMode] = useState<'browse' | 'saved'>('browse')
  /** True when detail was opened from a list (show back); false for direct map/search picks. */
  const [detailFromList, setDetailFromList] = useState(false)
  const [severityFocus, setSeverityFocus] = useState<SeverityFocus | null>(null)
  const favourites = useFavourites()

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    fetchRepos(controller.signal)
      .then((entries) => {
        setRepos(entries.map(mapRepoToListItem))
        setRawMapRepos(
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
      {
        ...(riskFilter === 'all' ? {} : { risk: riskFilter }),
        limit: FINDINGS_PAGE_SIZE,
        offset: (findingsPage - 1) * FINDINGS_PAGE_SIZE,
      },
      controller.signal,
    )
      .then((page) => {
        setFindings(page.items)
        setFindingsTotal(page.total)
        setFindingsLoading(false)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const message = err instanceof Error ? err.message : 'Failed to load findings'
        setFindingsError(message)
        setFindingsLoading(false)
      })
    return () => controller.abort()
  }, [tab, riskFilter, findingsPage])

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

  const filteredMapRepos = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return rawMapRepos
    return rawMapRepos.filter((repo) => {
      const name = repo.name.toLowerCase()
      const language = (repo.language || '').toLowerCase()
      const overview = repo.overview.toLowerCase()
      if (searchScope === 'name') return name.includes(q)
      if (searchScope === 'language') return language.includes(q)
      if (searchScope === 'category') {
        return overview.includes(q) || name.includes(q)
      }
      return name.includes(q) || language.includes(q) || overview.includes(q)
    })
  }, [rawMapRepos, searchQuery, searchScope])

  const flowerLayout = useMemo(
    () => layoutFlowerMap(filteredMapRepos),
    [filteredMapRepos],
  )

  const mapFitPoints = useMemo(() => flowerLayout.flowers.flatMap(flower => {
    const bounds = flowerWorldBounds(flower)
    return [{ x: bounds.minX, y: bounds.minY }, { x: bounds.maxX, y: bounds.maxY }]
  }), [flowerLayout.flowers])

  const severityMatchedIds = useMemo(() => {
    if (!severityFocus) return null
    const ids = new Set<string>()
    for (const repo of flowerLayout.repos) {
      if (repo.flowerId !== severityFocus.flowerId) continue
      if (severityFocus.tone == null || repo.vulnerabilityTone === severityFocus.tone) {
        ids.add(repo.id)
      }
    }
    return ids
  }, [flowerLayout.repos, severityFocus])

  const filteredRepos = useMemo(() => {
    const ids = new Set(filteredMapRepos.map((repo) => repo.id))
    return repos.filter((repo) => {
      if (!ids.has(repo.id)) return false
      if (severityMatchedIds && !severityMatchedIds.has(repo.id)) return false
      return true
    })
  }, [repos, filteredMapRepos, severityMatchedIds])

  const severityFocusLabel = useMemo(() => {
    if (!severityFocus) return null
    const flower = flowerLayout.flowers.find((f) => f.id === severityFocus.flowerId)
    const bucket =
      flower?.label === 'No GitHub advisories'
        ? 'No advisories'
        : flower?.label ?? severityFocus.flowerId
    if (severityFocus.tone == null) return bucket
    const toneLabel =
      severityFocus.tone === 'high'
        ? 'High'
        : severityFocus.tone === 'medium'
          ? 'Med'
          : 'Low'
    return `${toneLabel} · ${bucket}`
  }, [severityFocus, flowerLayout.flowers])

  const {
    setViewportSize,
    fitToRepos,
    fitToBoundsAnimated,
    pan,
    zoomIn,
    zoomOut,
    zoomByFactor,
    focusOnPoint,
    camera,
  } = mapCamera

  useEffect(() => {
    if (flowerLayout.repos.length === 0) return
    fitToRepos(mapFitPoints, true)
  }, [mapFitPoints, fitToRepos])

  const handleViewportChange = useCallback(
    (width: number, height: number) => {
      setViewportSize(width, height)
      if (flowerLayout.repos.length > 0) fitToRepos(mapFitPoints)
    },
    [fitToRepos, mapFitPoints, setViewportSize],
  )

  /** When the sidebar is closed, reserve its width so focus lands in the map that remains. */
  const sidebarFocusInsets = useCallback((): { right?: number; bottom?: number } => {
    if (sidebarOpen) return {}
    if (typeof window !== 'undefined' && window.matchMedia('(max-width: 720px)').matches) {
      // Mobile uses a bottom sheet; keep vertical framing for now.
      return {}
    }
    return { right: sidebarWidth }
  }, [sidebarOpen, sidebarWidth])

  const handleZoomToFlower = useCallback(
    (flower: (typeof flowerLayout.flowers)[number]) => {
      setSelectedId(null)
      // Generous padding so the bloom + label sit centered with white margin.
      fitToBoundsAnimated(flowerWorldBounds(flower), 96, sidebarFocusInsets())
    },
    [fitToBoundsAnimated, sidebarFocusInsets],
  )

  const handlePinnedSeverityChange = useCallback((focus: SeverityFocus | null) => {
    setSeverityFocus(focus)
    setSelectedId(null)
    setListMode('browse')
    setView('list')
    setSidebarOpen(focus != null)
  }, [])

  const handleBackgroundClick = useCallback(() => {
    setSidebarOpen(false)
    setSelectedId(null)
    setSeverityFocus(null)
    setListMode('browse')
    setDetailFromList(false)
    setTab('map')
    setView('list')
  }, [])

  const showDetailBack = detailFromList
  const backLabel =
    listMode === 'saved'
      ? '← Favourites'
      : severityFocus
        ? '← All repositories'
        : tab === 'findings'
          ? '← Findings'
          : '← Repositories'

  function handleBack() {
    if (selectedId && detailFromList) {
      setSelectedId(null)
      setDetailFromList(false)
      setView('list')
      return
    }
    if (severityFocus) {
      setSeverityFocus(null)
      setSelectedId(null)
      setDetailFromList(false)
      setSidebarOpen(false)
      return
    }
    if (selectedId) {
      setSelectedId(null)
      setDetailFromList(false)
      setView('list')
      if (tab !== 'findings') setSidebarOpen(false)
      return
    }
    setSidebarOpen(false)
  }

  function handleViewSaved() {
    // Toggle Saved closed when already open.
    if (listMode === 'saved' && sidebarOpen) {
      setSelectedId(null)
      setSeverityFocus(null)
      setDetailFromList(false)
      setListMode('browse')
      setTab('map')
      setView('list')
      setSidebarOpen(false)
      return
    }
    setSelectedId(null)
    setSeverityFocus(null)
    setDetailFromList(false)
    setListMode('saved')
    setTab('map')
    setView('list')
    setSidebarOpen(true)
  }

  function handleSelectRepo(id: string, fromList = false) {
    const insets = sidebarFocusInsets()
    setSelectedId(id)
    setSidebarOpen(true)
    setDetailFromList(fromList)
    if (!fromList) {
      setSeverityFocus(null)
      if (listMode === 'saved') setListMode('browse')
    }
    const point = flowerLayout.repos.find((repo) => repo.id === id)
      ?? filteredMapRepos.find((repo) => repo.id === id)
      ?? rawMapRepos.find((repo) => repo.id === id)
    if (point) {
      focusOnPoint({ x: point.x, y: point.y }, point.importance, insets)
    }
  }

  function handleTabChange(next: TopNavbarTab) {
    // Toggle Findings closed when already open.
    if (
      next === 'findings' &&
      tab === 'findings' &&
      sidebarOpen &&
      listMode !== 'saved'
    ) {
      setTab('map')
      setSelectedId(null)
      setSeverityFocus(null)
      setDetailFromList(false)
      setListMode('browse')
      setSidebarOpen(false)
      setView('list')
      return
    }
    setTab(next)
    setSelectedId(null)
    setSeverityFocus(null)
    setDetailFromList(false)
    setListMode('browse')
    // Map stays visible; Findings opens the findings drawer.
    setSidebarOpen(next === 'findings')
    setView('list')
  }

  const findingsActive =
    tab === 'findings' && sidebarOpen && listMode !== 'saved'
  const savedActive = listMode === 'saved' && sidebarOpen

  const selectedMapRepo =
    selectedId == null
      ? null
      : flowerLayout.repos.find((repo) => repo.id === selectedId)
        ?? filteredMapRepos.find((repo) => repo.id === selectedId)
        ?? rawMapRepos.find((repo) => repo.id === selectedId)
        ?? null

  let detailPane = null
  if (selectedId) {
    if (detailLoading) {
      detailPane = (
        <RepoSidebarSkeleton
          repoId={selectedId}
          language={selectedMapRepo?.language}
          onBack={showDetailBack ? handleBack : undefined}
          backLabel={backLabel}
        />
      )
    } else if (detailError) {
      detailPane = (
        <aside className="repo-sidebar repo-sidebar--status" role="alert">
          <p>Could not load {selectedId}.</p>
          <p className="repo-sidebar__error-detail">{detailError}</p>
          {showDetailBack ? (
            <button type="button" className="repo-sidebar__back" onClick={handleBack}>
              {backLabel}
            </button>
          ) : null}
        </aside>
      )
    } else if (detail) {
      detailPane = (
        <RepoSidebar
          {...detail}
          onBack={showDetailBack ? handleBack : undefined}
          backLabel={backLabel}
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
        onSelectRepo={(id) => handleSelectRepo(id, true)}
        onCreateList={favourites.createList}
        onRenameList={favourites.renameList}
        onDeleteList={favourites.deleteList}
        onRemoveFromList={favourites.removeFromList}
      />
    ) : tab === 'findings' ? (
      <FindingsView
        findings={findings}
        total={findingsTotal}
        page={findingsPage}
        pageSize={FINDINGS_PAGE_SIZE}
        loading={findingsLoading}
        error={findingsError}
        selectedId={selectedId}
        riskFilter={riskFilter}
        onRiskFilterChange={(next) => {
          setRiskFilter(next)
          setFindingsPage(1)
        }}
        onPageChange={setFindingsPage}
        onSelectFinding={(id) => handleSelectRepo(id, true)}
      />
    ) : (
      <RepoListSidebar
        title={severityFocusLabel ? severityFocusLabel : undefined}
        metaLabel={
          severityFocusLabel
            ? 'Matching repositories on the map'
            : undefined
        }
        repos={filteredRepos}
        loading={loading}
        error={error}
        selectedId={selectedId}
        onSelectRepo={(id) => handleSelectRepo(id, true)}
        countLabel={
          severityFocus || searchQuery.trim()
            ? `${filteredRepos.length} ${filteredRepos.length === 1 ? 'repository' : 'repositories'} found`
            : undefined
        }
      />
    )

  return (
    <div className="app-shell">
      <div className="app-shell__main">
        <TopNavbar
          activeTab={tab}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(open => !open)}
          onTabChange={handleTabChange}
          onViewSaved={handleViewSaved}
          findingsActive={findingsActive}
          savedActive={savedActive}
        />
        <main className="app-shell__map" aria-label="Repository galaxy map">
          <GalaxyMap
            repos={flowerLayout.repos}
            flowers={flowerLayout.flowers}
            camera={camera}
            selectedId={selectedId}
            pinnedSeverity={severityFocus}
            onSelectRepo={handleSelectRepo}
            onPinnedSeverityChange={handlePinnedSeverityChange}
            onBackgroundClick={handleBackgroundClick}
            onViewportChange={handleViewportChange}
            onPan={pan}
            onZoomByFactor={zoomByFactor}
            onZoomToFlower={handleZoomToFlower}
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
      </div>
      <SidebarPanel
        open={sidebarOpen}
        width={sidebarWidth}
        onWidthChange={setSidebarWidth}
      >
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
