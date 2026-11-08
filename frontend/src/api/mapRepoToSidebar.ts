import type {
  AdvisoryView,
  EvidenceView,
  RepoSidebarProps,
  VerdictView,
} from '../components/RepoSidebar'
import type { Advisory, RepoDetail, Verdict } from './types'

function formatStars(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}m`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, '')}k`
  return String(n)
}

function daysBetween(iso: string | null | undefined, now = Date.now()): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return null
  return Math.max(0, Math.floor((now - t) / 86_400_000))
}

function formatDaysAgo(days: number | null): string {
  if (days == null) return '—'
  if (days === 0) return 'today'
  if (days === 1) return '1 day'
  return `${days} days`
}

function formatReleaseAge(days: number | null): string {
  if (days == null) return '—'
  if (days === 0) return 'today'
  if (days === 1) return '1 day ago'
  return `${days} days ago`
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  return `${Math.round(n * 100)}%`
}

function formatUnavailable(n: number | null | undefined, asPercent = false): string {
  if (n == null || Number.isNaN(n)) return 'unavailable'
  return asPercent ? formatPct(n) : String(n)
}

function importanceLevel(importance: number | null | undefined): string {
  if (importance == null) return '—'
  if (importance >= 4) return 'High'
  if (importance >= 2) return 'Medium'
  return 'Low'
}

function importancePct(importance: number | null | undefined): number {
  if (importance == null) return 0
  return Math.max(0, Math.min(100, Math.round((importance / 8) * 100)))
}

function barPct(value: number, peer: number): number {
  const max = Math.max(value, peer, 1)
  return Math.round((value / max) * 100)
}

function mapVerdict(v: Verdict | null | undefined): VerdictView | null {
  if (!v) return null
  return {
    riskLevel: v.risk_level,
    confidence: Math.round(v.confidence * 100),
    headline: v.headline,
    explanation: v.explanation,
    changedSinceLast: v.changed_since_last,
    investigatedAt: formatDate(v.investigated_at),
    toolCalls: v.tool_calls,
  }
}

function mapEvidence(verdict: Verdict | null | undefined): EvidenceView[] {
  if (!verdict?.evidence?.length) return []
  return verdict.evidence.map((e) => ({
    signal: e.signal,
    tool: e.tool,
    value: e.value == null ? null : String(e.value),
  }))
}

function mapAdvisories(items: Advisory[]): AdvisoryView[] {
  return items.map((a) => ({
    ghsaId: a.ghsa_id,
    cveId: a.cve_id,
    severity: a.severity,
    cvss: a.cvss_score,
    cwes: a.cwes,
    bucket: a.vuln_bucket,
    summary: a.summary,
    publishedAt: formatDate(a.published_at),
  }))
}

function advisoriesLabel(
  fetchStatus: string | null | undefined,
  count: number,
): string {
  const status = (fetchStatus || 'not_fetched').toLowerCase()
  if (status === 'failed' || status === 'not_fetched') return 'Advisories unavailable'
  if (count === 0) return 'No GitHub advisories'
  return `${count} advisories`
}

export function mapRepoToSidebar(repo: RepoDetail): RepoSidebarProps {
  const m = repo.metrics
  const pushDays = daysBetween(m.pushed_at)
  const releaseDays =
    m.days_since_release != null ? Math.floor(m.days_since_release) : daysBetween(m.last_release_at)
  const now = m.commits_90d ?? 0
  const prior = m.commits_prev_90d ?? 0
  const advisories = mapAdvisories(repo.advisories || [])
  const alternatives = (repo.verdict?.alternatives || []).filter(
    (a) => a && a.includes('/') && !a.startsWith('['),
  )

  const healthMetrics = [
    {
      key: m.commit_trend_pct == null ? '—' : `${Math.round(m.commit_trend_pct)}%`,
      value: 'commit trend (90d)',
    },
    {
      key: formatUnavailable(m.maintainer_reply_rate, true),
      value: 'maintainer reply rate',
    },
    {
      key: formatUnavailable(m.contributors),
      value: 'contributors',
    },
    {
      key: formatUnavailable(m.top_contributor_share, true),
      value: 'top-contributor share',
    },
  ]

  const score =
    repo.health_score == null ? '—/100' : `${Math.round(repo.health_score)}/100`

  return {
    language: repo.language ?? 'Unknown',
    starsLabel: formatStars(repo.stars),
    // MVP scrape leaves dependents as 0/unknown — hide the chip rather than show "deps 0".
    dependentsLabel:
      repo.dependents != null && repo.dependents > 0
        ? formatStars(repo.dependents)
        : null,
    name: repo.name,
    owner: repo.owner,
    repoId: repo.repo_id,
    githubUrl: repo.github_url,
    isArchived: Boolean(repo.is_archived),
    status: repo.status ?? 'watchlist',
    category: repo.category,
    topics: repo.topics || [],
    vulnBuckets: repo.vuln_buckets || [],
    description:
      repo.description?.trim() ||
      'No description available.',
    summary: repo.summary?.trim() || null,
    lastPush: formatDaysAgo(pushDays),
    lastRelease: formatReleaseAge(releaseDays),
    lastReleaseDate: formatDate(m.last_release_at),
    commits90d: m.commits_90d == null ? '—' : String(m.commits_90d),
    commitsNow: now,
    commitsPrior: prior,
    commitsNowPct: barPct(now, prior),
    commitsPriorPct: barPct(prior, now),
    openIssues: m.open_issues == null ? '—' : String(m.open_issues),
    openPrs: m.open_prs == null ? '—' : String(m.open_prs),
    importanceLevel: importanceLevel(repo.importance),
    importancePct: importancePct(repo.importance),
    importanceRaw: repo.importance == null ? null : Number(repo.importance.toFixed(2)),
    healthScore: score,
    healthStatus: repo.status,
    healthMetrics,
    verdict: mapVerdict(repo.verdict),
    previousVerdict: mapVerdict(repo.previous_verdict),
    evidence: mapEvidence(repo.verdict),
    alternatives,
    advisories,
    advisoriesLabel: advisoriesLabel(repo.advisory_fetch_status, advisories.length),
    advisoryFetchStatus: repo.advisory_fetch_status,
    maxSeverity: repo.max_severity,
    maxCvss: repo.max_cvss,
  }
}
