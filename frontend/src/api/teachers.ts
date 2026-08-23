import { apiJson } from './client'

export type SchoolLevel = 'elementary' | 'secondary'

export type Teacher = {
  id: number
  full_name: string
  email: string | null
  phone: string | null
  home_classroom_id: number | null
  home_classroom: { id: number; display_name: string } | null
}

export type TeacherBrief = Pick<Teacher, 'id' | 'full_name'>

export type TeacherPayload = {
  full_name: string
  email: string | null
  phone: string | null
  home_classroom_id: number | null
}

export function listTeachers() {
  return apiJson<Teacher[]>('/api/teachers/')
}

export function createTeacher(payload: TeacherPayload) {
  return apiJson<Teacher>('/api/teachers/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateTeacher(id: number, payload: TeacherPayload) {
  return apiJson<Teacher>(`/api/teachers/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteTeacher(id: number) {
  return apiJson<void>(`/api/teachers/${id}`, { method: 'DELETE' })
}
