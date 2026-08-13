/** JSON fetch helper; paths are proxied `/api/*` in dev. */

export class ApiError extends Error {
  status: number
  body: string

  constructor(status: number, body: string) {
    super(body || `HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

function formatErrorItem(item: unknown): string {
  if (typeof item === 'string') return item
  if (item && typeof item === 'object') {
    const o = item as { msg?: string; message?: string }
    if (typeof o.msg === 'string') return o.msg
    if (typeof o.message === 'string') return o.message
  }
  return JSON.stringify(item)
}

/** Human-readable text from FastAPI / network errors. */
export function extractApiError(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const data = JSON.parse(err.body) as {
        detail?: unknown
        errors?: unknown
        message?: unknown
      }
      const detail = data.detail ?? data
      if (typeof detail === 'string' && detail.trim()) return detail
      if (detail && typeof detail === 'object') {
        const d = detail as { errors?: unknown; message?: unknown }
        if (Array.isArray(d.errors) && d.errors.length) {
          return d.errors.map(formatErrorItem).join('\n')
        }
        if (typeof d.message === 'string' && d.message.trim()) return d.message
      }
      if (Array.isArray(detail) && detail.length) {
        return detail.map(formatErrorItem).join('\n')
      }
      if (Array.isArray(data.errors) && data.errors.length) {
        return data.errors.map(formatErrorItem).join('\n')
      }
      if (typeof data.message === 'string' && data.message.trim()) return data.message
    } catch {
      /* not JSON */
    }
    return err.body || err.message
  }
  return err instanceof Error ? err.message : String(err)
}

export async function apiJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, text)
  }
  if (res.status === 204) {
    return undefined as T
  }
  return (text ? JSON.parse(text) : null) as T
}
