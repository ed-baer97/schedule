import { apiJson } from './client'

export type ClassroomTeacher = {
  id: number
  full_name: string
}

export type Classroom = {
  id: number
  number: string
  name: string | null
  floor: number | null
  building: string | null
  classes_capacity: number | null
  display_name: string
  subject_id: number | null
  is_exclusive: boolean
  subject: { id: number; name: string; display_color: string } | null
  teachers: ClassroomTeacher[]
}

export type ClassroomBrief = Pick<Classroom, 'id' | 'display_name'>

export type ClassroomPayload = {
  number: string
  name: string | null
  floor: number | null
  building: string | null
  classes_capacity: number
  subject_id: number | null
  is_exclusive: boolean
  teacher_ids: number[]
}

export function listClassrooms() {
  return apiJson<Classroom[]>('/api/classrooms/')
}

export function createClassroom(payload: ClassroomPayload) {
  return apiJson<Classroom>('/api/classrooms/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateClassroom(id: number, payload: ClassroomPayload) {
  return apiJson<Classroom>(`/api/classrooms/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteClassroom(id: number) {
  return apiJson<void>(`/api/classrooms/${id}`, { method: 'DELETE' })
}
