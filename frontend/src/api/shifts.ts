import { apiJson } from './client'

export type LessonTime = {
  id: number
  day_of_week: number
  lesson_number: number
  time_start: string
  time_end: string
}

export type Shift = {
  id: number
  name: string
  school_level: string
  school_level_display: string
  start_lesson: number
  lessons_count: number
  working_days: number
  max_lessons_per_day: number
  class_hour_day: number | null
  class_hour_start: string | null
  class_hour_end: string | null
  lesson_times: LessonTime[]
}

export type ShiftBrief = Pick<
  Shift,
  | 'id'
  | 'name'
  | 'school_level'
  | 'working_days'
  | 'max_lessons_per_day'
  | 'start_lesson'
  | 'lessons_count'
>

export type ShiftPayload = {
  name: string
  school_level: string
  start_lesson: number
  lessons_count: number
  working_days: number
  max_lessons_per_day: number
  class_hour_day: number | null
  class_hour_start: string | null
  class_hour_end: string | null
}

export type BellRow = { time_start: string; time_end: string }
export type BellState = { common: Record<string, BellRow>; class_day: Record<string, BellRow> }

export function listShifts() {
  return apiJson<Shift[]>('/api/shifts/')
}

export function createShift(payload: ShiftPayload) {
  return apiJson<{ id: number }>('/api/shifts/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateShift(id: number, payload: ShiftPayload) {
  return apiJson<void>(`/api/shifts/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function applyShiftLessonTimes(shiftId: number, bell: BellState) {
  return apiJson<{ inserted: number; warnings: string[] }>(
    `/api/shifts/${shiftId}/lesson-times`,
    { method: 'PUT', body: JSON.stringify(bell) },
  )
}

export function deleteShift(id: number) {
  return apiJson<void>(`/api/shifts/${id}`, { method: 'DELETE' })
}
