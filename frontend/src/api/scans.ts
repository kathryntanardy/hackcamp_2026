export type ScanFinding = {
  ghsa_id?: string | null
  file?: string | null
  line?: number | null
  severity: string
  cwe?: string | null
  title: string
  description: string
  recommendation: string
  workaround?: string | null
  patched_versions?: string | null
  advisory_url?: string | null
  cve_id?: string | null
  vuln_bucket?: string | null
  code_url?: string | null
  code_fix?: string | null
  report_url?: string | null
}

export type SecurityScan = {
  repo_id: string
  mode: 'advisories' | 'code'
  commit_sha: string | null
  model: string
  files: string[]
  advisory_ids: string[]
  summary: string
  findings: ScanFinding[]
  scanned_at: string
}

async function readError(res: Response, fallback: string): Promise<Error> {
  const body = await res.json().catch(() => null)
  return new Error(body?.detail || `${fallback} (${res.status})`)
}

export async function runScan(repoId: string): Promise<SecurityScan> {
  const res = await fetch(`/api/scans/${repoId}`, { method: 'POST' })
  if (!res.ok) throw await readError(res, 'Scan failed')
  return res.json() as Promise<SecurityScan>
}

// One request per repo at a time: switching tabs (or React StrictMode re-running effects)
// must not start a second paid Gemini scan while the first is still running.
const inflight = new Map<string, Promise<SecurityScan>>()

/** Stored scan if there is one, otherwise run a fresh one. */
export function loadOrRunScan(repoId: string, fresh = false): Promise<SecurityScan> {
  const key = `${repoId}|${fresh}`
  const pending = inflight.get(key)
  if (pending) return pending
  const promise = (async () => {
    if (!fresh) {
      const res = await fetch(`/api/scans/${repoId}`)
      if (res.ok) return res.json() as Promise<SecurityScan>
      if (res.status !== 404) throw await readError(res, 'Failed to load scan')
    }
    return runScan(repoId)
  })().finally(() => inflight.delete(key))
  inflight.set(key, promise)
  return promise
}
