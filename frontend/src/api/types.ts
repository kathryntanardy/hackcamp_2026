export type FindingListEntry = {
  repo_id: string
  name: string | null
  language: string | null
  importance: number | null
  health_score: number | null
  category: string | null
  vuln_buckets: string[]
  days_since_release?: number | null
  advisory_count?: number | null
  max_severity?: string | null
  max_cvss?: number | null
  run_id: string
  risk_level: string
  confidence: number
  headline: string
  explanation: string
  evidence: unknown[]
  changed_since_last: string | null
  alternatives: string[]
  tool_calls: number
  trace_id: string | null
  investigated_at: string
  in_latest_run: boolean | null
}

export type RepoListEntry = {
  repo_id: string
  name: string
  owner: string
  language: string | null
  health_score: number | null
  status: string | null
  importance: number | null
  stars: number | null
  is_archived: boolean | null
  category: string | null
  /** Prefer string[]; warehouse may also send a JSON/Python-repr array string. */
  vuln_buckets: string[] | string | null
  advisory_count: number | null
  max_severity: string | null
  max_cvss: number | null
  risk_level: string | null
  changed_since_last: string | null
  investigated: boolean | null
  investigated_in_latest_run: boolean | null
  summary: string | null
  x: number | null
  y: number | null
  cat_x: number | null
  cat_y: number | null
}

/** Matches hackcamp.agent.findings.evidence struct (value is STRING in UC). */
export type EvidenceItem = {
  signal: string
  tool: string
  value: string | null
}

export type Verdict = {
  run_id: string
  risk_level: string
  confidence: number
  headline: string
  explanation: string
  evidence: EvidenceItem[]
  changed_since_last: string | null
  alternatives: string[]
  tool_calls: number
  trace_id: string | null
  investigated_at: string
}

export type Advisory = {
  ghsa_id: string
  cve_id: string | null
  severity: string | null
  cvss_score: number | null
  cwes: string[]
  vuln_bucket: string | null
  summary: string | null
  published_at: string | null
}

export type RepoMetrics = {
  days_since_release: number | null
  commit_trend_pct: number | null
  pushed_at: string | null
  last_release_at: string | null
  commits_90d: number | null
  commits_prev_90d: number | null
  open_issues: number | null
  open_prs: number | null
  contributors: number | null
  maintainer_reply_rate: number | null
  top_contributor_share: number | null
}

export type RepoDetail = {
  repo_id: string
  name: string
  owner: string
  language: string | null
  stars: number | null
  dependents: number | null
  is_archived: boolean | null
  health_score: number | null
  status: string | null
  importance: number | null
  category: string | null
  vuln_buckets: string[]
  advisory_count: number | null
  max_severity: string | null
  max_cvss: number | null
  description: string | null
  topics: string[]
  summary: string | null
  advisory_fetch_status: string | null
  github_url: string
  metrics: RepoMetrics
  verdict: Verdict | null
  previous_verdict: Verdict | null
  advisories: Advisory[]
}
