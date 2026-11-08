import type { FindingListEntry } from './types'

export type FindingsQuery = {
  language?: string
  risk?: string
  limit?: number
  offset?: number
}

export type FindingsPage = {
  items: FindingListEntry[]
  total: number
  limit: number
  offset: number
}

export async function fetchFindings(
  query: FindingsQuery = {},
  signal?: AbortSignal,
): Promise<FindingsPage> {
  const params = new URLSearchParams()
  if (query.language) params.set('language', query.language)
  if (query.risk) params.set('risk', query.risk)
  if (query.limit != null) params.set('limit', String(query.limit))
  if (query.offset != null) params.set('offset', String(query.offset))
  const qs = params.toString()
  const res = await fetch(`/api/findings${qs ? `?${qs}` : ''}`, { signal })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(detail || `Failed to load findings (${res.status})`)
  }
  return res.json() as Promise<FindingsPage>
}
