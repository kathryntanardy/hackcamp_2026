export type EvidenceItem = {
  signal: string
  tool: string
  value: string | number | null
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
