import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { fetchRepo } from './api/repos'
import { mapRepoToSidebar } from './api/mapRepoToSidebar'
import { RepoSidebar, type RepoSidebarProps } from './components/RepoSidebar'
import './styles.css'

/** Hardcoded selection until the galaxy map wires click → repo_id.
 * Prefer a repo that already has an agent finding so Evidence + Agent Process populate.
 * lodash/lodash has advisories/gold data but no investigation finding yet. */
const SELECTED_REPO_ID = 'moment/moment'

function App() {
  const [sidebar, setSidebar] = useState<RepoSidebarProps | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    fetchRepo(SELECTED_REPO_ID, controller.signal)
      .then((repo) => {
        setSidebar(mapRepoToSidebar(repo))
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const message = err instanceof Error ? err.message : 'Failed to load repo'
        setError(message)
        setLoading(false)
      })
    return () => controller.abort()
  }, [])

  return (
    <div className="app-shell">
      <main className="app-shell__main" aria-label="Map placeholder" />
      {loading ? (
        <aside className="repo-sidebar repo-sidebar--status" aria-busy="true">
          <p>Loading {SELECTED_REPO_ID}…</p>
        </aside>
      ) : error ? (
        <aside className="repo-sidebar repo-sidebar--status" role="alert">
          <p>Could not load {SELECTED_REPO_ID}.</p>
          <p className="repo-sidebar__error-detail">{error}</p>
          <p className="repo-sidebar__error-hint">
            Start the backend (`uvicorn app.main:app --reload` in `backend/`) so
            Vite can proxy `/api`.
          </p>
        </aside>
      ) : sidebar ? (
        <RepoSidebar {...sidebar} />
      ) : null}
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
)
