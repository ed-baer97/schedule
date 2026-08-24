import { apiJson } from './client'
import type { SchoolLevel } from '../domain/schoolLevel'

export type Subject = {
  id: number
  name: string
  color: string | null
  display_color: string
  requires_fixed_classroom: boolean
  default_classroom_id: number | null
  default_classroom: { display_name: string } | null
}

export type SubjectPayload = {
  name: string
  color: string
  requires_fixed_classroom: boolean
  default_classroom_id: number | null
}

export type SubjectAssignmentClassRow = {
  id: number
  name: string
  grade: number
  hours_per_week: number
  teacher_ids: number[]
  is_split: boolean
}

export type SubjectAssignmentsView = {
  subject: {
    id: number
    name: string
    display_color: string
  }
  school_level: string
  classes: SubjectAssignmentClassRow[]
  attached_teachers: { id: number; full_name: string }[]
  all_teachers: { id: number; full_name: string }[]
}

export type SubjectAssignmentsPayload = {
  school_level: SchoolLevel
  teacher_ids: number[]
  selections: Record<string, number[]>
}

export function listSubjects(schoolLevel?: SchoolLevel | 'all') {
  const path =
    schoolLevel && schoolLevel !== 'all'
      ? `/api/subjects/?school_level=${schoolLevel}`
      : '/api/subjects/'
  return apiJson<Subject[]>(path)
}

export function getColorPalette() {
  return apiJson<string[]>('/api/subjects/meta/color-palette')
}

export function updateSubjectColor(id: number, color: string) {
  return apiJson<{ display_color: string }>(`/api/subjects/${id}/color`, {
    method: 'PATCH',
    body: JSON.stringify({ color }),
  })
}

export function createSubject(payload: SubjectPayload) {
  return apiJson<Subject>('/api/subjects/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateSubject(id: number, payload: SubjectPayload) {
  return apiJson<Subject>(`/api/subjects/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteSubject(id: number) {
  return apiJson<void>(`/api/subjects/${id}`, { method: 'DELETE' })
}

export function getSubjectAssignments(subjectId: number, schoolLevel: SchoolLevel) {
  return apiJson<SubjectAssignmentsView>(
    `/api/subjects/${subjectId}/assignments?school_level=${schoolLevel}`,
  )
}

export function saveSubjectAssignments(subjectId: number, payload: SubjectAssignmentsPayload) {
  return apiJson<{ ok: boolean; errors: string[] }>(
    `/api/subjects/${subjectId}/assignments`,
    { method: 'POST', body: JSON.stringify(payload) },
  )
}
