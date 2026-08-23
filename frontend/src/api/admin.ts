import { apiJson } from './client'

export type AdminSchool = {
  id: number
  name: string
  slug: string
  is_active: boolean
  admins_count: number
}

export type PlatformDashboard = {
  schools_total: number
  schools_active: number
  schools_inactive: number
  schools_without_admin: number
  school_admins_total: number
  school_admins_active: number
  jobs_active: number
  teachers_total: number
  classes_total: number
}

export type SchoolAdmin = {
  id: number
  email: string
  role: string
  is_active: boolean
  created_at?: string | null
  password?: string | null
}

export type AdminCreateResult = {
  id: number
  email: string
  password: string
  message: string
}

export function fetchPlatformDashboard() {
  return apiJson<PlatformDashboard>('/api/admin/dashboard')
}

export function listAdminSchools() {
  return apiJson<AdminSchool[]>('/api/admin/schools')
}

export function createAdminSchool(payload: { name: string; slug: string | null }) {
  return apiJson<AdminSchool>('/api/admin/schools', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateAdminSchool(id: number, payload: { is_active: boolean }) {
  return apiJson<AdminSchool>(`/api/admin/schools/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function listSchoolAdmins(schoolId: number) {
  return apiJson<SchoolAdmin[]>(`/api/admin/schools/${schoolId}/admins`)
}

export function createSchoolAdmin(schoolId: number, payload: { email: string; password: string }) {
  return apiJson<AdminCreateResult>(`/api/admin/schools/${schoolId}/admins`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateAdminUser(
  userId: number,
  payload: { password?: string; is_active?: boolean },
) {
  return apiJson<SchoolAdmin>(`/api/admin/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}
