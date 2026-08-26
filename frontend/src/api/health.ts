import { apiJson } from './client'

export type HealthResponse = {
  status: string
  database: {
    connected: boolean
    schema_ready: boolean
    missing_tables?: string[]
    missing_columns?: Record<string, string[]>
    message?: string
    error?: string
  }
}

export function fetchHealth() {
  return apiJson<HealthResponse>('/api/health')
}
