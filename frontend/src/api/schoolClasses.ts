import { apiJson } from './client'

export type SchoolClass = {
  id: number
  name: string
  grade: number
  school_level: string
  school_level_display: string
  shift_id: number | null
  home_classroom_id: number | null
  homeroom_teacher_id: number | null
  shift: { id: number; name: string } | null
  home_classroom: { display_name: string } | null
  homeroom_teacher: { id: number; full_name: string } | null
}

export type SchoolClassBrief = Pick<SchoolClass, 'id' | 'name' | 'school_level'>

export type SchoolClassPayload = {
  name: string
  school_level: string
  shift_id: number | null
  home_classroom_id: number | null
  homeroom_teacher_id: number | null
}

export function listSchoolClasses() {
  return apiJson<SchoolClass[]>('/api/school-classes/')
}

export function createSchoolClass(payload: SchoolClassPayload) {
  return apiJson<SchoolClass>('/api/school-classes/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateSchoolClass(id: number, payload: SchoolClassPayload) {
  return apiJson<SchoolClass>(`/api/school-classes/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteSchoolClass(id: number) {
  return apiJson<void>(`/api/school-classes/${id}`, { method: 'DELETE' })
}

export function batchAssignShift(classIds: number[], shiftId: number | null) {
  return apiJson<void>('/api/school-classes/batch-shift', {
    method: 'POST',
    body: JSON.stringify({ class_ids: classIds, shift_id: shiftId }),
  })
}
