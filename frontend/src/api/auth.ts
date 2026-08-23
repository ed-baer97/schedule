import { apiJson } from './client'

export type AuthUser = {
  id: number
  email: string
  role: string
  school_id: number | null
  school_name: string | null
}

export function fetchMe() {
  return apiJson<AuthUser>('/api/auth/me')
}

export function login(email: string, password: string) {
  return apiJson<AuthUser>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function logout() {
  return apiJson<void>('/api/auth/logout', { method: 'POST' })
}
