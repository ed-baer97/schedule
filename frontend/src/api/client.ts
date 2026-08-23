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

const FIELD_RU: Record<string, string> = {
  name: 'название',
  full_name: 'ФИО',
  email: 'email',
  password: 'пароль',
}

function formatErrorItem(item: unknown): string {
  if (typeof item === 'string') return item
  if (item && typeof item === 'object') {
    const o = item as { msg?: string; message?: string; loc?: unknown; type?: string }
    const locParts = Array.isArray(o.loc)
      ? o.loc.filter((x) => typeof x === 'string' && x !== 'body' && x !== 'query' && x !== 'path')
      : []
    const field = locParts.length ? String(locParts[locParts.length - 1]) : ''
    const raw =
      (typeof o.msg === 'string' && o.msg) || (typeof o.message === 'string' && o.message) || ''
    const type = o.type ?? ''
    const empty =
      type.includes('missing') ||
      type.includes('too_short') ||
      /field required|at least 1 character/i.test(raw)

    if (field === 'name' && empty) return 'Укажите название смены'
    const label = FIELD_RU[field]
    if (label && empty) return `Укажите ${label}`
    if (label && raw) return `${label}: ${raw}`
    if (raw) return raw
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

let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

export async function apiJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(path, {
    ...init,
    credentials: 'include',
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })
  const text = await res.text()
  if (res.status === 401 && !path.startsWith('/api/auth/')) {
    onUnauthorized?.()
  }
  if (!res.ok) {
    throw new ApiError(res.status, text)
  }
  if (res.status === 204) {
    return undefined as T
  }
  return (text ? JSON.parse(text) : null) as T
}
