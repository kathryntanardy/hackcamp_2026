import type { FindingListEntry } from './types'

export type FindingsQuery = {
  language?: string
  risk?: string
}

export async function fetchFindings(
  query: FindingsQuery = {},
  signal?: AbortSignal,
): Promise<FindingListEntry[]> {
  const params = new URLSearchParams()
  if (query.language) params.set('language', query.language)
  if (query.risk) params.set('risk', query.risk)
  const qs = params.toString()
  const res = await fetch(`/api/findings${qs ? `?${qs}` : ''}`, { signal })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(detail || `Failed to load findings (${res.status})`)
  }
  return res.json() as Promise<FindingListEntry[]>
}
