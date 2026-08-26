import { apiJson } from './client'

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
}

export type TeacherLoadSubject = {
  subject_id: number
  subject_name: string
  color: string
  hours: number
}

export type TeacherLoadShift = {
  id: number
  name: string
  school_level: string
  hours: number
}

export type TeacherLoad = {
  id: number
  full_name: string
  subjects: TeacherLoadSubject[]
  shifts: TeacherLoadShift[]
  total_hours: number
  unassigned_shift_hours: number
  has_classes_without_shift: boolean
}

export function listTeachers() {
  return apiJson<Teacher[]>('/api/teachers/')
}

export function listTeacherLoad() {
  return apiJson<TeacherLoad[]>('/api/teachers/load')
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
