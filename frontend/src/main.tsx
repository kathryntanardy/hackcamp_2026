import { maintenanceToneLabel } from './map/health'
import { FLOWER_SCENE } from './map/flowerScene'
import { StrictMode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { fetchFindings, type FindingsSort } from './api/findings'
import { mapRepoToListItem } from './api/mapRepoToListItem'
import { mapRepoToMapPoint } from './api/mapRepoToMapPoint'
import { mapRepoToSidebar } from './api/mapRepoToSidebar'
import { fetchRepo, fetchRepos } from './api/repos'
import { fetchSearch } from './api/search'
import type { FindingListEntry } from './api/types'
import {
  FindingsView,
  type FindingsRiskFilter,
} from './components/FindingsView'
import { FavouritesSidebar } from './components/FavouritesSidebar'
import { GalaxyMap } from './components/GalaxyMap'
import { MapSearchBar, type MapSearchScope } from './components/MapSearchBar'
import {
  RepoListSidebar,
  type RepoListItem,
} from './components/RepoListSidebar'
import { RepoSidebar, type RepoSidebarProps } from './components/RepoSidebar'
import { RepoSidebarSkeleton } from './components/RepoSidebarSkeleton'
import { SidebarPanel } from './components/SidebarPanel'
import { TopNavbar, type TopNavbarTab } from './components/TopNavbar'
import { useFavourites } from './favourites/useFavourites'
import { boundsOf } from './map/camera'
import {
  flowerWorldBounds,
  layoutFlowerMap,
  type SeverityFocus,
} from './map/flowers'
import type { MapRepo, WorldBounds } from './map/types'
import { useMapCamera } from './map/useMapCamera'
import { localSearchIds, mergeSearchIds, searchResultItems } from './map/search'
import './styles.css'

const FINDINGS_PAGE_SIZE = 50
/** Wait for typing to settle before hitting Vector Search (local matches show instantly). */
const SEARCH_DEBOUNCE_MS = 450
/** Short queries stay local — VS embedding latency isn't worth it for 1–2 chars. */
const SEARCH_VS_MIN_CHARS = 3
/** Screen padding when framing search hits (wider than flower zoom). */
const SEARCH_FIT_PADDING = 180

/** Expand match bounds so a single star / tight cluster isn't face-filling. */
function searchViewBounds(matches: Pick<MapRepo, 'x' | 'y'>[]): WorldBounds | null {
  const bounds = boundsOf(matches)
  if (!bounds) return null
  const span = Math.max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY)
  const pad = Math.max(18, span * 0.7)
  return {
    minX: bounds.minX - pad,
    maxX: bounds.maxX + pad,
    minY: bounds.minY - pad,
    maxY: bounds.maxY + pad,
  }
}


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
  const [findingsCategory, setFindingsCategory] = useState<string | null>(null)
  const [findingsBucket, setFindingsBucket] = useState<string | null>(null)
  const [findingsLanguage, setFindingsLanguage] = useState<string | null>(null)
  const [findingsSort, setFindingsSort] = useState<FindingsSort>('severity')

  const [tab, setTab] = useState<TopNavbarTab>('map')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(580)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchScope, setSearchScope] = useState<MapSearchScope>('vulnerabilities')
  /** null = no active search; array (maybe empty) = latest hits for the query. */
  const [searchMatchIds, setSearchMatchIds] = useState<string[] | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const searchAppliedKey = useRef<string | null>(null)

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
        ...(findingsCategory ? { category: findingsCategory } : {}),
        ...(findingsBucket ? { vuln_bucket: findingsBucket } : {}),
        ...(findingsLanguage ? { language: findingsLanguage } : {}),
        sort: findingsSort,
        limit: FINDINGS_PAGE_SIZE,
        offset: (findingsPage - 1) * FINDINGS_PAGE_SIZE,
      },
      controller.signal,
    )
      .then((page) => {
        if (controller.signal.aborted) return
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
  }, [
    tab,
    riskFilter,
    findingsCategory,
    findingsBucket,
    findingsLanguage,
    findingsSort,
    findingsPage,
  ])

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
        if (controller.signal.aborted) return
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

  // Preserve the scene, bringing rare buckets into its slots for search and selection.
  const flowerGrouping = searchScope === 'category' ? 'category' : 'vulnerabilities'
  const layoutPriority = useMemo(() => {
    if (selectedId) return new Set([selectedId, ...(searchMatchIds ?? [])])
    return searchMatchIds?.length ? new Set(searchMatchIds) : null
  }, [selectedId, searchMatchIds])
  const flowerLayout = useMemo(
    () => layoutFlowerMap(rawMapRepos, layoutPriority, flowerGrouping),
    [rawMapRepos, layoutPriority, flowerGrouping],
  )

  const hasMapRepos = rawMapRepos.length > 0
  const mapFitPoints = useMemo(() => hasMapRepos ? [
    { x: 0, y: 0 }, { x: FLOWER_SCENE.width, y: FLOWER_SCENE.height },
  ] : [], [hasMapRepos])
  const searchResults = useMemo(
    () => searchResultItems(repos, searchMatchIds),
    [repos, searchMatchIds],
  )

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

  const searchMatchSet = useMemo(() => {
    // Dim only when there is at least one hit; zero matches leave the map alone (F14).
    if (!searchMatchIds || searchMatchIds.length === 0) return null
    return new Set(searchMatchIds)
  }, [searchMatchIds])

  const findingLanguages = useMemo(() => {
    const set = new Set<string>()
    for (const repo of rawMapRepos) {
      if (repo.language) set.add(repo.language)
    }
    return [...set].sort((a, b) => a.localeCompare(b))
  }, [rawMapRepos])

  const filteredRepos = useMemo(() => {
    const hitSet =
      searchMatchIds == null ? null : new Set(searchMatchIds)
    return repos.filter((repo) => {
      if (hitSet && !hitSet.has(repo.id)) return false
      if (severityMatchedIds && !severityMatchedIds.has(repo.id)) return false
      return true
    })
  }, [repos, searchMatchIds, severityMatchedIds])

  const severityFocusLabel = useMemo(() => {
    if (!severityFocus) return null
    const flower = flowerLayout.flowers.find((f) => f.id === severityFocus.flowerId)
    const bucket =
      flower?.label === 'No GitHub advisories'
        ? 'No advisories'
        : flower?.label ?? severityFocus.flowerId
    if (severityFocus.tone == null) return bucket
    const toneLabel = `${maintenanceToneLabel(severityFocus.tone)} maintenance`
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
    maxScale,
  } = mapCamera

  useEffect(() => {
    if (flowerLayout.repos.length === 0) return
    fitToRepos(mapFitPoints, true, 0)
  }, [mapFitPoints, fitToRepos])

  const handleViewportChange = useCallback(
    (width: number, height: number) => {
      setViewportSize(width, height)
      if (flowerLayout.repos.length > 0) fitToRepos(mapFitPoints, false, 0)
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

  const applySearchHits = useCallback(
    (ids: string[], key: string) => {
      if (searchAppliedKey.current === key) return
      searchAppliedKey.current = key
      if (ids.length === 0) return
      const idSet = new Set(ids)
      const matches = flowerLayout.repos.filter((repo) => idSet.has(repo.id))
      if (matches.length === 0) return
      const view = searchViewBounds(matches)
      if (ids.length === 1 && matches.length === 1) {
        const point = matches[0]
        setSelectedId(point.id)
        setSidebarOpen(true)
        setDetailFromList(false)
        setListMode('browse')
        setSeverityFocus(null)
        setTab('map')
        setView('detail')
        const flower = flowerLayout.flowers.find((flower) => flower.id === point.flowerId)
        if (flower) {
          fitToBoundsAnimated(flowerWorldBounds(flower), 56, sidebarFocusInsets())
        } else if (view) {
          fitToBoundsAnimated(view, SEARCH_FIT_PADDING, sidebarFocusInsets())
        }
        return
      }
      setSelectedId(null)
      setView('list')
      if (view) {
        fitToBoundsAnimated(view, SEARCH_FIT_PADDING, sidebarFocusInsets())
      }
    },
    [fitToBoundsAnimated, flowerLayout.repos, flowerLayout.flowers, sidebarFocusInsets],
  )

  // Fetch only when the query, scope, or corpus changes. Opening a drawer must
  // not restart the request or replace semantic matches with local matches.
  useEffect(() => {
    const trimmed = searchQuery.trim()
    if (!trimmed) {
      setSearchMatchIds(null)
      setSearchLoading(false)
      setSearchError(null)
      return
    }
    const localIds = localSearchIds(trimmed, rawMapRepos, repos, searchScope)
    setSearchMatchIds(localIds)
    setSearchError(null)
    if (searchScope !== 'all' || trimmed.length < SEARCH_VS_MIN_CHARS) {
      setSearchLoading(false)
      return
    }
    setSearchLoading(true)
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      fetchSearch({ q: trimmed }, controller.signal)
        .then((res) => {
          if (controller.signal.aborted) return
          setSearchMatchIds(mergeSearchIds(trimmed, rawMapRepos, localIds, res.repo_ids))
          setSearchLoading(false)
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return
          setSearchLoading(false)
          setSearchError(err instanceof Error ? err.message : 'Search failed')
        })
    }, SEARCH_DEBOUNCE_MS)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [rawMapRepos, repos, searchQuery, searchScope])

  // Apply camera framing after matching repos have been placed into the scene.
  useEffect(() => {
    const trimmed = searchQuery.trim()
    if (!trimmed) {
      if (searchAppliedKey.current != null) {
        searchAppliedKey.current = null
        setSelectedId(null)
        setView('list')
        fitToRepos(mapFitPoints, true, 0)
      }
      return
    }
    if (tab !== 'map' || searchLoading || searchMatchIds == null) return
    const delay = searchScope === 'all' && trimmed.length >= SEARCH_VS_MIN_CHARS
      ? 0 : SEARCH_DEBOUNCE_MS
    const timer = window.setTimeout(() => {
      applySearchHits(searchMatchIds, `${searchScope}:${trimmed}:${searchMatchIds.join(',')}`)
    }, delay)
    return () => window.clearTimeout(timer)
  }, [applySearchHits, fitToRepos, mapFitPoints, searchQuery, searchScope,
      searchLoading, searchMatchIds, tab])

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
    const focusedLayout = flowerLayout.repos.some((repo) => repo.id === id)
      ? flowerLayout
      : layoutFlowerMap(rawMapRepos, new Set([id, ...(searchMatchIds ?? [])]), flowerGrouping)
    const point = focusedLayout.repos.find((repo) => repo.id === id)
    if (point) {
      const flower = focusedLayout.flowers.find((flower) => flower.id === point.flowerId)
      if (flower) fitToBoundsAnimated(flowerWorldBounds(flower), 56, insets)
      else focusOnPoint({ x: point.x, y: point.y }, insets)
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
        categoryFilter={findingsCategory}
        bucketFilter={findingsBucket}
        languageFilter={findingsLanguage}
        sort={findingsSort}
        languages={findingLanguages}
        onRiskFilterChange={(next) => {
          setRiskFilter(next)
          setFindingsPage(1)
        }}
        onCategoryFilterChange={(next) => {
          setFindingsCategory(next)
          setFindingsPage(1)
        }}
        onBucketFilterChange={(next) => {
          setFindingsBucket(next)
          setFindingsPage(1)
        }}
        onLanguageFilterChange={(next) => {
          setFindingsLanguage(next)
          setFindingsPage(1)
        }}
        onSortChange={(next) => {
          setFindingsSort(next)
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
        onViewSaved={handleViewSaved}
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
          findingsActive={findingsActive}
          savedActive={savedActive}
        />
        <main className="app-shell__map" aria-label="Repository galaxy map">
          <GalaxyMap
            repos={flowerLayout.repos}
            flowers={flowerLayout.flowers}
            camera={camera}
            maxScale={maxScale}
            selectedId={selectedId}
            matchIds={searchMatchSet}
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
            results={searchResults}
            loading={searchLoading}
            error={searchError}
            onQueryChange={(query) => {
              setSearchQuery(query)
              setSeverityFocus(null)
              setTab('map')
              setListMode('browse')
            }}
            onScopeChange={(scope) => {
              setSearchScope(scope)
              setSeverityFocus(null)
              setSelectedId(null)
              searchAppliedKey.current = null
              fitToRepos(mapFitPoints, true, 0)
            }}
            onSelectResult={handleSelectRepo}
            onZoomIn={() => zoomIn()}
            onZoomOut={() => zoomOut()}
            zoomOutDisabled={camera.scale <= mapCamera.minScale + 0.000001}
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

// Keep one app root across Vite updates so old map animation loops are cleaned up.
const root = (import.meta.hot?.data.root as Root | undefined)
  ?? createRoot(document.getElementById('root')!)
if (import.meta.hot) import.meta.hot.data.root = root
root.render(
  <StrictMode><App /></StrictMode>,
)
