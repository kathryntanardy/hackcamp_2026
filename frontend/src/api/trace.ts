export type TraceStep = {
  order: number
  span_id?: string | null
  kind: string
  tool_name: string | null
  phase: string | null
  status: string | null
  result_summary: string | null
  reasoning: string | null
  inputs?: Record<string, unknown> | null
  outputs?: Record<string, unknown> | null
}

export type TracePayload = {
  repo_id: string
  run_id: string
  trace_id: string | null
  status: string
  explanation?: string | null
  steps: TraceStep[]
}

export async function fetchTrace(
  repoId: string,
  signal?: AbortSignal,
): Promise<TracePayload> {
  const res = await fetch(`/api/findings/${repoId}/trace`, { signal })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(detail || `Failed to load trace (${res.status})`)
  }
  return res.json() as Promise<TracePayload>
}
