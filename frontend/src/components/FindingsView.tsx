import type { FindingListEntry } from '../api/types'

export type FindingsRiskFilter = 'all' | 'at_risk' | 'watchlist' | 'healthy' | 'inconclusive'

export type FindingsViewProps = {
  findings?: FindingListEntry[]
  total?: number
  page?: number
  pageSize?: number
  loading?: boolean
  error?: string | null
  selectedId?: string | null
  riskFilter?: FindingsRiskFilter
  onRiskFilterChange?: (risk: FindingsRiskFilter) => void
  onPageChange?: (page: number) => void
  onSelectFinding?: (repoId: string) => void
}

const DEFAULT_PAGE_SIZE = 50

function riskClass(risk: string | null | undefined): string {
  const r = (risk || '').toLowerCase()
  if (r === 'at_risk') return 'is-at-risk'
  if (r === 'watchlist') return 'is-watchlist'
  if (r === 'healthy') return 'is-healthy'
  return 'is-inconclusive'
}

function formatRisk(risk: string | null | undefined): string {
  return (risk || 'unknown').replaceAll('_', ' ')
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const FILTERS: { id: FindingsRiskFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'at_risk', label: 'At risk' },
  { id: 'watchlist', label: 'Watchlist' },
  { id: 'healthy', label: 'Healthy' },
  { id: 'inconclusive', label: 'Inconclusive' },
]

export function FindingsView({
  findings = [],
  total = 0,
  page = 1,
  pageSize = DEFAULT_PAGE_SIZE,
  loading = false,
  error = null,
  selectedId = null,
  riskFilter = 'all',
  onRiskFilterChange,
  onPageChange,
  onSelectFinding,
}: FindingsViewProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(Math.max(1, page), pageCount)
  const rangeStart = total === 0 ? 0 : (safePage - 1) * pageSize + 1
  const rangeEnd = Math.min(safePage * pageSize, total)

  return (
    <aside className="findings-view" aria-label="Agent findings">
      <header className="findings-view__top">
        <div className="findings-view__meta">
          <span>Investigation findings</span>
        </div>
      </header>

      <div className="findings-view__hero">
        <h1 className="findings-view__title">Findings</h1>
        <p className="findings-view__subtitle">
          Investigations sorted by severity. Open a row to inspect that repo on the map.
        </p>
        <div className="findings-view__filters" role="toolbar" aria-label="Risk filter">
          {FILTERS.map((filter) => (
            <button
              key={filter.id}
              type="button"
              className={`findings-view__filter${riskFilter === filter.id ? ' is-active' : ''}`}
              aria-pressed={riskFilter === filter.id}
              onClick={() => onRiskFilterChange?.(filter.id)}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      <div className="findings-view__body">
        {loading ? (
          <p className="findings-view__status">Loading findings…</p>
        ) : error ? (
          <p className="findings-view__status is-error" role="alert">
            {error}
          </p>
        ) : total === 0 ? (
          <p className="findings-view__status">No findings for this filter yet.</p>
        ) : (
          <>
            <p className="findings-view__count">
              {total} {total === 1 ? 'finding' : 'findings'}
              <span className="findings-view__count-range">
                {' '}
                · showing {rangeStart}–{rangeEnd}
              </span>
            </p>
            <ul className="findings-list">
              {findings.map((finding) => {
                const confidence = Math.round((finding.confidence ?? 0) * 100)
                return (
                  <li key={`${finding.repo_id}-${finding.run_id}`}>
                    <button
                      type="button"
                      className={`findings-row${selectedId === finding.repo_id ? ' is-selected' : ''}`}
                      aria-current={selectedId === finding.repo_id ? 'true' : undefined}
                      onClick={() => onSelectFinding?.(finding.repo_id)}
                    >
                      <div className="findings-row__top">
                        <span className={`status-chip ${riskClass(finding.risk_level)}`}>
                          {formatRisk(finding.risk_level)}
                        </span>
                        {finding.in_latest_run ? (
                          <span className="findings-row__new">New</span>
                        ) : null}
                        <span className="findings-row__meta">
                          {confidence}% confidence · {formatDate(finding.investigated_at)}
                        </span>
                      </div>
                      <p className="findings-row__name">{finding.name || finding.repo_id}</p>
                      <p className="findings-row__headline">
                        {finding.headline || 'No headline.'}
                      </p>
                      <div className="findings-row__footer">
                        <span>{finding.language || '—'}</span>
                        <span>{finding.category || '—'}</span>
                        {finding.changed_since_last ? (
                          <span>{finding.changed_since_last.replaceAll('_', ' ')}</span>
                        ) : null}
                      </div>
                    </button>
                  </li>
                )
              })}
            </ul>
          </>
        )}
      </div>

      {!loading && !error && total > pageSize ? (
        <nav className="findings-pagination" aria-label="Findings pages">
          <button
            type="button"
            className="findings-pagination__btn"
            disabled={safePage <= 1}
            onClick={() => onPageChange?.(safePage - 1)}
          >
            Previous
          </button>
          <p className="findings-pagination__status">
            Page {safePage} of {pageCount}
          </p>
          <button
            type="button"
            className="findings-pagination__btn"
            disabled={safePage >= pageCount}
            onClick={() => onPageChange?.(safePage + 1)}
          >
            Next
          </button>
        </nav>
      ) : null}
    </aside>
  )
}
