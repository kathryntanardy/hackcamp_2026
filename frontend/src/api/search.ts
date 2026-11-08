export type SearchQuery = {
  q: string
  language?: string
  category?: string
  status?: string
  vuln_bucket?: string
  investigated_only?: boolean
}

export type SearchResult = {
  query: string
  repo_ids: string[]
}

export async function fetchSearch(
  query: SearchQuery,
  signal?: AbortSignal,
): Promise<SearchResult> {
  const params = new URLSearchParams()
  params.set('q', query.q)
  if (query.language) params.set('language', query.language)
  if (query.category) params.set('category', query.category)
  if (query.status) params.set('status', query.status)
  if (query.vuln_bucket) params.set('vuln_bucket', query.vuln_bucket)
  if (query.investigated_only) params.set('investigated_only', 'true')
  const res = await fetch(`/api/search?${params}`, { signal })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(detail || `Search failed (${res.status})`)
  }
  return res.json() as Promise<SearchResult>
}
