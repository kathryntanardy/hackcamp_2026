import { maintenanceStatusLabel, MAINTENANCE_HEALTH_DESCRIPTION } from '../map/health'
import { useEffect, useState } from 'react'
import languageIcon from '../assets/icons/language.svg'
import starIcon from '../assets/icons/star.svg'
import starOutlineIcon from '../assets/icons/star-outline.svg'
import arrowUpRightIcon from '../assets/icons/arrow-up-right.svg'
import gitCommitIcon from '../assets/icons/git-commit.svg'
import chevronUpIcon from '../assets/icons/chevron-up.svg'
import { fetchTrace, type TracePayload } from '../api/trace'
import type { FavouriteList } from '../favourites/types'
import { FavouriteStarButton } from './FavouriteStarButton'

export type RepoSidebarTab = 'overview' | 'agent'

export type EvidenceView = {
  signal: string
  tool: string
  value: string | null
}

export type VerdictView = {
  riskLevel: string
  confidence: number
  headline: string
  explanation: string
  changedSinceLast: string | null
  investigatedAt: string
  toolCalls: number
}

export type AdvisoryView = {
  ghsaId: string
  cveId: string | null
  severity: string | null
  cvss: number | null
  cwes: string[]
  bucket: string | null
  summary: string | null
  publishedAt: string
}

/** GitHub Advisory Database page for a GHSA or CVE id. */
function githubAdvisoryUrl(id: string): string {
  return `https://github.com/advisories/${encodeURIComponent(id.trim())}`
}

/** Mitre CWE definition page from labels like "CWE-25" or "25". */
function cweUrl(cwe: string): string | null {
  const match = cwe.trim().match(/^(?:CWE-)?(\d+)$/i)
  if (!match) return null
  return `https://cwe.mitre.org/data/definitions/${match[1]}.html`
}

export type RepoSidebarProps = {
  language?: string
  starsLabel?: string
  dependentsLabel?: string | null
  name?: string
  owner?: string
  repoId?: string
  githubUrl?: string
  isArchived?: boolean
  status?: string
  category?: string | null
  topics?: string[]
  vulnBuckets?: string[]
  description?: string
  summary?: string | null
  lastPush?: string
  lastRelease?: string
  lastReleaseDate?: string
  commits90d?: string
  commitsNow?: number
  commitsPrior?: number
  commitsNowPct?: number
  commitsPriorPct?: number
  openIssues?: string
  openPrs?: string
  importanceLevel?: string
  importancePct?: number
  importanceRaw?: number | null
  healthScore?: string
  healthStatus?: string | null
  healthMetrics?: { key: string; value: string }[]
  verdict?: VerdictView | null
  previousVerdict?: VerdictView | null
  evidence?: EvidenceView[]
  alternatives?: string[]
  advisories?: AdvisoryView[]
  advisoriesLabel?: string
  advisoryFetchStatus?: string | null
  maxSeverity?: string | null
  maxCvss?: number | null
  onBack?: () => void
  backLabel?: string
  favouriteLists?: FavouriteList[]
  isFavourite?: boolean
  favouriteListsForRepo?: FavouriteList[]
  onToggleFavourite?: (repoId: string) => void
  onToggleInList?: (listId: string, repoId: string) => void
  onCreateFavouriteList?: (name: string) => string
}

function statusClass(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'healthy') return 'is-healthy'
  if (s === 'at_risk') return 'is-at-risk'
  if (s === 'ignored') return 'is-ignored'
  if (s === 'inconclusive') return 'is-inconclusive'
  return 'is-watchlist'
}

function severityClass(severity: string | null | undefined): string {
  const s = (severity || '').toLowerCase()
  if (s === 'critical' || s === 'high') return 'is-high'
  if (s === 'medium' || s === 'moderate') return 'is-medium'
  return 'is-low'
}

function stepTitle(step: { kind: string; tool_name: string | null }): string {
  if (step.kind === 'decision') return 'Model decision'
  if (step.tool_name) return step.tool_name
  return step.kind || 'Step'
}

function hasInputs(inputs: Record<string, unknown> | null | undefined): boolean {
  if (!inputs || typeof inputs !== 'object') return false
  return Object.keys(inputs).length > 0
}

function formatStepInputs(inputs: Record<string, unknown>): string {
  try {
    return JSON.stringify(inputs, null, 2)
  } catch {
    return String(inputs)
  }
}

export function RepoSidebar({
  language = '—',
  starsLabel = '—',
  dependentsLabel = null,
  name = 'Repository',
  owner = '—',
  repoId = '—',
  githubUrl = '#',
  isArchived = false,
  status = 'watchlist',
  category = null,
  topics = [],
  vulnBuckets = [],
  description = 'Loading repository…',
  summary: _summary = null,
  lastPush = '—',
  lastRelease = '—',
  lastReleaseDate = '—',
  commits90d = '—',
  commitsNow = 0,
  commitsPrior = 0,
  commitsNowPct = 0,
  commitsPriorPct = 0,
  openIssues = '—',
  openPrs = '—',
  importanceLevel = '—',
  importancePct = 0,
  importanceRaw = null,
  healthScore = '—/100',
  healthStatus = null,
  healthMetrics = [],
  verdict = null,
  previousVerdict = null,
  evidence = [],
  alternatives = [],
  advisories = [],
  advisoriesLabel = 'No GitHub advisories',
  maxSeverity = null,
  maxCvss = null,
  onBack,
  backLabel = '← Repositories',
  favouriteLists = [],
  isFavourite = false,
  favouriteListsForRepo = [],
  onToggleFavourite,
  onToggleInList,
  onCreateFavouriteList,
}: RepoSidebarProps) {
  const [tab, setTab] = useState<RepoSidebarTab>('overview')
  const [evidenceOpen, setEvidenceOpen] = useState(true)
  const [altsOpen, setAltsOpen] = useState(true)
  const [advisoriesOpen, setAdvisoriesOpen] = useState(true)
  const [trace, setTrace] = useState<TracePayload | null>(null)
  const [traceError, setTraceError] = useState<string | null>(null)
  const [traceLoading, setTraceLoading] = useState(false)
  const nowPct = Math.max(0, Math.min(100, commitsNowPct))
  const priorPct = Math.max(0, Math.min(100, commitsPriorPct))

  useEffect(() => {
    if (tab !== 'agent' || !repoId || repoId === '—') return
    const controller = new AbortController()
    setTraceLoading(true)
    setTraceError(null)
    fetchTrace(repoId, controller.signal)
      .then((payload) => {
        setTrace(payload)
        setTraceLoading(false)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setTrace(null)
        setTraceError(err instanceof Error ? err.message : 'Trace unavailable')
        setTraceLoading(false)
      })
    return () => controller.abort()
  }, [tab, repoId])

  return (
    <aside className="repo-sidebar" aria-label="Repository details">
      <header className="repo-sidebar__top">
        <div className="repo-sidebar__meta">
          {onBack ? (
            <button type="button" className="repo-sidebar__back" onClick={onBack}>
              {backLabel}
            </button>
          ) : null}
          <span className="repo-sidebar__meta-item">
            <img src={languageIcon} alt="" width={17} height={17} />
            {language}
          </span>
          <span aria-hidden="true">|</span>
          <span className="repo-sidebar__meta-item">
            <img src={starIcon} alt="" width={17} height={17} />
            {starsLabel}
          </span>
          {dependentsLabel ? (
            <>
              <span aria-hidden="true">|</span>
              <span className="repo-sidebar__meta-item" title="Dependents">
                deps {dependentsLabel}
              </span>
            </>
          ) : null}
        </div>
      </header>

      <div className="repo-sidebar__title-block">
        <div className="repo-sidebar__title-row">
          {repoId && repoId !== '—' && onToggleFavourite && onToggleInList && onCreateFavouriteList ? (
            <FavouriteStarButton
              repoId={repoId}
              saved={isFavourite}
              lists={favouriteLists}
              listsForRepo={favouriteListsForRepo}
              onToggleFavourite={onToggleFavourite}
              onToggleInList={onToggleInList}
              onCreateList={onCreateFavouriteList}
            />
          ) : (
            <span className="repo-sidebar__star-btn" aria-hidden="true">
              <img src={starOutlineIcon} alt="" width={15} height={14} />
            </span>
          )}
          <div className="repo-sidebar__title-main">
            <div className="repo-sidebar__name-row">
              <div className="repo-sidebar__name-wrap">
                <h1 className="repo-sidebar__name">{name}</h1>
                <a
                  className="repo-sidebar__ext-link"
                  href={githubUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label="Open on GitHub"
                >
                  <img src={arrowUpRightIcon} alt="" width={29} height={29} />
                </a>
              </div>
              <p className="repo-sidebar__repo-id">{repoId}</p>
            </div>
            <div className="repo-sidebar__owner-row">
              <p className="repo-sidebar__owner">{owner}</p>
              <div className="chip-row">
                <span className={`status-chip ${statusClass(status)}`}>
                  {maintenanceStatusLabel(status)}
                </span>
                {isArchived ? <span className="status-chip is-ignored">archived</span> : null}
                {category ? <span className="chip">{category}</span> : null}
              </div>
            </div>
            {topics.length > 0 ? (
              <div className="chip-row chip-row--wrap">
                {topics.slice(0, 8).map((t) => (
                  <span className="chip chip--quiet" key={t}>{t}</span>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <nav className="repo-sidebar__tabs" aria-label="Repository sections">
        <button
          type="button"
          className={`repo-sidebar__tab${tab === 'overview' ? ' is-active' : ''}`}
          aria-current={tab === 'overview' ? 'page' : undefined}
          onClick={() => setTab('overview')}
        >
          Overview
        </button>
        <button
          type="button"
          className={`repo-sidebar__tab${tab === 'agent' ? ' is-active' : ''}`}
          aria-current={tab === 'agent' ? 'page' : undefined}
          onClick={() => setTab('agent')}
        >
          Agent Process
        </button>
      </nav>

      <div className="repo-sidebar__body">
        {tab === 'overview' ? (
          <>
            <p className="repo-sidebar__description">{description}</p>

            <section className="section" aria-labelledby="key-signals-heading">
              <h2 id="key-signals-heading" className="section-heading">Key Signals</h2>
              <div className="signal-grid">
                <article className="signal-card">
                  <div className="signal-stack">
                    <p className="signal-label">
                      <img src={gitCommitIcon} alt="" width={24} height={24} />
                      Last push
                    </p>
                    <p className="signal-value">{lastPush}</p>
                  </div>
                  <hr className="signal-divider" />
                  <div className="signal-stack">
                    <p className="signal-label">Last release</p>
                    <p className="signal-value">{lastRelease}</p>
                    <p className="signal-sub">{lastReleaseDate}</p>
                  </div>
                </article>

                <article className="signal-card">
                  <div className="signal-stack">
                    <p className="signal-label">Commits, 90d</p>
                    <p className="signal-value">{commits90d}</p>
                  </div>
                  <div className="bar-row">
                    <div className="bar-row__labels">
                      <span>Now</span>
                      <span>{commitsNow}</span>
                    </div>
                    <div className="bar" aria-hidden="true">
                      <div className="bar__fill" style={{ width: `${nowPct}%` }} />
                    </div>
                  </div>
                  <div className="bar-row">
                    <div className="bar-row__labels">
                      <span>Prior</span>
                      <span>{commitsPrior}</span>
                    </div>
                    <div className="bar" aria-hidden="true">
                      <div className="bar__fill" style={{ width: `${priorPct}%` }} />
                    </div>
                  </div>
                </article>

                <article className="signal-card">
                  <div className="signal-stack" style={{ gap: 8, width: '100%' }}>
                    <p className="signal-label">Open work</p>
                    <div className="open-work">
                      <div className="open-work__col">
                        <p className="signal-value">{openIssues}</p>
                        <p className="signal-sub">Issues</p>
                      </div>
                      <div className="open-work__col">
                        <p className="signal-value">{openPrs}</p>
                        <p className="signal-sub">Pull Requests</p>
                      </div>
                    </div>
                  </div>
                </article>

                <article className="signal-card importance-card">
                  <div className="importance-head">
                    <p className="signal-label">
                      <img src={starIcon} alt="" width={17} height={17} />
                      Importance
                    </p>
                    <span className="badge">{importanceLevel}</span>
                  </div>
                  <div className="bar-row">
                    <div className="bar" aria-hidden="true">
                      <div className="bar__fill" style={{ width: `${importancePct}%` }} />
                    </div>
                    <p className="signal-sub">
                      Based on stars (log scale)
                      {importanceRaw != null ? ` · ${importanceRaw}` : ''}
                    </p>
                  </div>
                </article>
              </div>
            </section>

            <section className="section" aria-labelledby="health-heading">
              <h2 id="health-heading" className="section-heading">Maintenance</h2>
              <p className="empty-note">{MAINTENANCE_HEALTH_DESCRIPTION}</p>
              <div className="health-row">
                <div className="health-score">
                  <p className="signal-value">{healthScore}</p>
                  <p className="signal-label">Maintenance score</p>
                  {healthStatus ? (
                    <span className={`status-chip ${statusClass(healthStatus)}`}>
                      {maintenanceStatusLabel(healthStatus)}
                    </span>
                  ) : null}
                </div>
                <div className="health-metrics">
                  {healthMetrics.map((m) => (
                    <div className="health-metric" key={`${m.key}-${m.value}`}>
                      <span className="health-metric__key">{m.key}</span>
                      <span className="health-metric__val">{m.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="section" aria-labelledby="advisories-heading">
              <div className="section-heading-row">
                <h2 id="advisories-heading" className="section-heading">Security advisories</h2>
                <button
                  type="button"
                  className="section-meta"
                  aria-expanded={advisoriesOpen}
                  onClick={() => setAdvisoriesOpen((v) => !v)}
                >
                  {advisoriesLabel}
                  <img
                    src={chevronUpIcon}
                    alt=""
                    width={24}
                    height={24}
                    className={advisoriesOpen ? undefined : 'is-collapsed'}
                  />
                </button>
              </div>
              {(maxSeverity || maxCvss != null) && advisories.length > 0 ? (
                <p className="section-subline">
                  Max severity {maxSeverity ?? '—'}
                  {maxCvss != null ? ` · CVSS ${maxCvss}` : ''}
                </p>
              ) : null}
              {vulnBuckets.length > 0 ? (
                <div className="chip-row chip-row--wrap">
                  {vulnBuckets.map((b) => (
                    <span className="chip" key={b}>{b}</span>
                  ))}
                </div>
              ) : null}
              {advisoriesOpen ? (
                advisories.length > 0 ? (
                  <ul className="advisory-list">
                    {advisories.map((a) => (
                      <li className="advisory-card" key={a.ghsaId}>
                        <div className="advisory-card__head">
                          <span className={`severity-chip ${severityClass(a.severity)}`}>
                            {a.severity ?? 'unknown'}
                          </span>
                          {a.bucket ? <span className="chip chip--quiet">{a.bucket}</span> : null}
                          {a.cvss != null ? <span className="advisory-card__cvss">CVSS {a.cvss}</span> : null}
                        </div>
                        <p className="advisory-card__ids">
                          {a.ghsaId ? (
                            <a
                              className="advisory-card__link"
                              href={githubAdvisoryUrl(a.ghsaId)}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {a.ghsaId}
                            </a>
                          ) : null}
                          {a.cveId ? (
                            <>
                              {' · '}
                              <a
                                className="advisory-card__link"
                                href={githubAdvisoryUrl(a.cveId)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {a.cveId}
                              </a>
                            </>
                          ) : null}
                          {a.publishedAt !== '—' ? ` · ${a.publishedAt}` : ''}
                        </p>
                        <p className="advisory-card__summary">{a.summary || 'No summary.'}</p>
                        {a.cwes.length > 0 ? (
                          <p className="advisory-card__cwes">
                            {a.cwes.map((cwe, index) => {
                              const href = cweUrl(cwe)
                              return (
                                <span key={`${a.ghsaId}-${cwe}`}>
                                  {index > 0 ? ', ' : null}
                                  {href ? (
                                    <a
                                      className="advisory-card__link"
                                      href={href}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      {cwe}
                                    </a>
                                  ) : (
                                    cwe
                                  )}
                                </span>
                              )
                            })}
                          </p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty-note">{advisoriesLabel}. Never treat this as “safe”.</p>
                )
              ) : null}
            </section>

            <section className="section" aria-labelledby="evidence-heading">
              <div className="section-heading-row">
                <h2 id="evidence-heading" className="section-heading">Evidence</h2>
                <button
                  type="button"
                  className="section-meta"
                  aria-expanded={evidenceOpen}
                  onClick={() => setEvidenceOpen((v) => !v)}
                >
                  {evidence.length} items
                  <img
                    src={chevronUpIcon}
                    alt=""
                    width={24}
                    height={24}
                    className={evidenceOpen ? undefined : 'is-collapsed'}
                  />
                </button>
              </div>
              {evidenceOpen ? (
                evidence.length > 0 ? (
                  <div className="evidence-list">
                    <div className="evidence-rail" aria-hidden="true">
                      {evidence.map((_, i) => (
                        <span
                          className="evidence-rail__dot"
                          key={i}
                          style={{ top: `${6 + i * 27}px` }}
                        />
                      ))}
                    </div>
                    <ul className="evidence-items">
                      {evidence.map((item) => (
                        <li key={`${item.tool}-${item.signal}`}>
                          <strong>{item.signal}</strong>
                          {item.value ? ` · ${item.value}` : ''}
                          <span className="evidence-items__tool"> via {item.tool}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p className="empty-note">No agent evidence yet for this repository.</p>
                )
              ) : null}
            </section>

            {alternatives.length > 0 ? (
              <section className="section" aria-labelledby="alternatives-heading">
                <div className="section-heading-row">
                  <h2 id="alternatives-heading" className="section-heading">Alternatives</h2>
                  <button
                    type="button"
                    className="section-meta"
                    aria-expanded={altsOpen}
                    onClick={() => setAltsOpen((v) => !v)}
                  >
                    {alternatives.length} options
                    <img
                      src={chevronUpIcon}
                      alt=""
                      width={24}
                      height={24}
                      className={altsOpen ? undefined : 'is-collapsed'}
                    />
                  </button>
                </div>
                {altsOpen ? (
                  <ul className="alt-list">
                    {alternatives.map((alt) => (
                      <li key={alt}>
                        <a href={`https://github.com/${alt}`} target="_blank" rel="noreferrer">
                          {alt}
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>
            ) : null}
          </>
        ) : (
          <>
            <section className="section" aria-labelledby="verdict-heading">
              <h2 id="verdict-heading" className="section-heading">Agent maintenance assessment</h2>
              {verdict ? (
                <div className="verdict-card">
                  <div className="verdict-card__head">
                    <span className={`status-chip ${statusClass(verdict.riskLevel)}`}>
                      {maintenanceStatusLabel(verdict.riskLevel)}
                    </span>
                    <span className="verdict-card__meta">
                      {verdict.confidence}% confidence · {verdict.investigatedAt}
                      {verdict.changedSinceLast ? ` · ${verdict.changedSinceLast.replaceAll('_', ' ')}` : ''}
                    </span>
                  </div>
                  <p className="verdict-card__headline">{verdict.headline}</p>
                  <p className="verdict-card__body">{verdict.explanation}</p>
                  {previousVerdict ? (
                    <p className="verdict-card__prev">
                      Previous: {maintenanceStatusLabel(previousVerdict.riskLevel)} on {previousVerdict.investigatedAt}
                    </p>
                  ) : null}
                </div>
              ) : (
                <p className="empty-note">Not investigated yet. Baseline maintenance status: {maintenanceStatusLabel(status)}.</p>
              )}
            </section>

            <section className="section" aria-labelledby="trace-heading">
              <h2 id="trace-heading" className="section-heading">How the agent decided</h2>
              {traceLoading ? <p className="empty-note">Loading trace…</p> : null}
              {traceError ? (
                <p className="empty-note">
                  {traceError.includes('404') || traceError.toLowerCase().includes('no finding')
                    ? 'No investigation finding yet — run the agent on this repo to populate the trace.'
                    : traceError}
                </p>
              ) : null}
              {trace && !traceLoading ? (
                trace.status === 'not_ready' || !(trace.steps?.length > 0) ? (
                  <p className="empty-note">
                    Trace steps are not ready for this finding yet — re-run the agent to export an
                    ordered decision trail.
                  </p>
                ) : (
                  <>
                    <p className="section-subline">
                      {trace.status}
                      {trace.trace_id ? ` · ${trace.trace_id}` : ''}
                      {` · ${trace.steps.length} steps`}
                    </p>
                    {trace.explanation ? (
                      <p className="repo-sidebar__summary">{trace.explanation}</p>
                    ) : null}
                    <ol className="trace-list">
                      {trace.steps.map((step) => (
                        <li
                          className="trace-step"
                          key={`${step.order}-${step.span_id ?? step.tool_name ?? step.kind}`}
                        >
                          <div className="trace-step__head">
                            <span className="trace-step__order">{step.order}</span>
                            <strong>{stepTitle(step)}</strong>
                            {step.phase ? (
                              <span className="chip chip--quiet">{step.phase}</span>
                            ) : null}
                            {step.status ? (
                              <span className="chip chip--quiet">{step.status}</span>
                            ) : null}
                          </div>
                          {hasInputs(step.inputs) ? (
                            <div className="trace-step__block">
                              <p className="trace-step__label">Inputs</p>
                              <pre className="trace-step__inputs">
                                {formatStepInputs(step.inputs as Record<string, unknown>)}
                              </pre>
                            </div>
                          ) : null}
                          <div className="trace-step__block">
                            <p className="trace-step__label">Result</p>
                            {step.result_summary ? (
                              <p className="trace-step__summary">{step.result_summary}</p>
                            ) : (
                              <p className="trace-step__summary is-muted">No result summary.</p>
                            )}
                          </div>
                          <div className="trace-step__block">
                            <p className="trace-step__label">Reasoning</p>
                            {step.reasoning ? (
                              <p className="trace-step__reasoning">{step.reasoning}</p>
                            ) : (
                              <p className="trace-step__summary is-muted">
                                No public decision summary.
                              </p>
                            )}
                          </div>
                        </li>
                      ))}
                    </ol>
                  </>
                )
              ) : null}
            </section>
          </>
        )}
      </div>
    </aside>
  )
}
