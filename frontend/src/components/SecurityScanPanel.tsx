import { useEffect, useState } from 'react'
import { loadOrRunScan, type ScanFinding, type SecurityScan } from '../api/scans'

function severityClass(severity: string | null | undefined): string {
  const s = (severity || '').toLowerCase()
  if (s === 'critical' || s === 'high') return 'is-high'
  if (s === 'medium' || s === 'moderate') return 'is-medium'
  return 'is-low'
}

/** Gemini answers in plain text with optional ``` code fences; render fences as code blocks. */
function RichText({ text }: { text: string }) {
  const parts = text.split(/```[a-zA-Z0-9_-]*\n?/)
  return (
    <>
      {parts.map((part, i) =>
        !part.trim() ? null : i % 2 === 1 ? (
          <pre className="trace-step__inputs" key={i}>{part.replace(/\n$/, '')}</pre>
        ) : (
          <p className="advisory-card__summary scan-text" key={i}>{part.trim()}</p>
        ),
      )}
    </>
  )
}

function FindingCard({ f }: { f: ScanFinding }) {
  return (
    <li className="advisory-card">
      <div className="advisory-card__head">
        <span className={`severity-chip ${severityClass(f.severity)}`}>{f.severity}</span>
        {f.vuln_bucket ? <span className="chip chip--quiet">{f.vuln_bucket}</span> : null}
        {f.patched_versions ? (
          <span className="chip chip--quiet">Fixed in {f.patched_versions}</span>
        ) : f.ghsa_id ? (
          <span className="chip chip--quiet">No patched version</span>
        ) : null}
      </div>
      <p className="verdict-card__headline scan-title">{f.title}</p>
      <p className="advisory-card__ids">
        {f.ghsa_id ? (
          f.advisory_url ? (
            <a href={f.advisory_url} target="_blank" rel="noreferrer">{f.ghsa_id}</a>
          ) : f.ghsa_id
        ) : null}
        {f.cve_id ? ` · ${f.cve_id}` : ''}
        {f.cwe ? `${f.ghsa_id ? ' · ' : ''}${f.cwe}` : ''}
        {f.file ? (
          <>
            {' · '}
            {f.code_url ? (
              <a href={f.code_url} target="_blank" rel="noreferrer">
                {f.file}{f.line ? `:${f.line}` : ''}
              </a>
            ) : f.file}
          </>
        ) : null}
      </p>
      <p className="advisory-card__summary">{f.description}</p>
      <div className="trace-step__block">
        <p className="trace-step__label">Recommended fix</p>
        <RichText text={f.recommendation} />
      </div>
      {f.workaround ? (
        <div className="trace-step__block">
          <p className="trace-step__label">Workaround</p>
          <RichText text={f.workaround} />
        </div>
      ) : null}
    </li>
  )
}

export function SecurityScanPanel({ repoId }: { repoId: string }) {
  const [scan, setScan] = useState<SecurityScan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [fresh, setFresh] = useState(0)

  useEffect(() => {
    let live = true
    setLoading(true)
    setError(null)
    if (fresh) setScan(null)
    loadOrRunScan(repoId, fresh > 0)
      .then((s) => live && setScan(s))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : 'Scan failed'))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [repoId, fresh])

  const isAdvisories = scan?.mode === 'advisories'

  return (
    <section className="section" aria-labelledby="security-heading">
      <div className="section-heading-row">
        <h2 id="security-heading" className="section-heading">
          {scan ? (isAdvisories ? 'Advisory fixes' : 'Code scan') : 'Security scan'}
        </h2>
        {scan && !loading ? (
          <button type="button" className="section-meta" onClick={() => setFresh((n) => n + 1)}>
            Rescan
          </button>
        ) : null}
      </div>

      {loading ? (
        <p className="empty-note">
          Gemini is checking this repo's GitHub advisories and source code… this takes 20–60 seconds.
        </p>
      ) : null}
      {error ? <p className="empty-note">Scan failed: {error}</p> : null}

      {scan && !loading ? (
        <>
          <p className="section-subline">
            {isAdvisories
              ? `${scan.advisory_ids.length} published advisor${scan.advisory_ids.length === 1 ? 'y' : 'ies'}`
              : `No published advisories · reviewed ${scan.files.length} source files`}
            {` · ${scan.model} · ${new Date(scan.scanned_at).toLocaleDateString()}`}
            {scan.commit_sha ? ` · ${scan.commit_sha.slice(0, 7)}` : ''}
          </p>
          {scan.summary ? <p className="repo-sidebar__summary">{scan.summary}</p> : null}
          {scan.findings.length > 0 ? (
            <ul className="advisory-list">
              {scan.findings.map((f, i) => (
                <FindingCard f={f} key={`${f.ghsa_id ?? f.file}-${i}`} />
              ))}
            </ul>
          ) : (
            <p className="empty-note">
              No vulnerabilities found in the files reviewed. That's not a guarantee the code is safe.
            </p>
          )}
        </>
      ) : null}
    </section>
  )
}
