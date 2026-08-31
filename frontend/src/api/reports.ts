import { apiJson } from './client'

export type ReportCell = {
  id: number
  day_of_week: number
  lesson_number: number
  subject_name: string
  subject_color: string
  teacher_name: string | null
  class_name?: string
  classroom_name: string | null
  group_number: number | null
}

export type ClassReport = {
  class_id: number
  class_name: string
  school_level: string
  day_names: string[]
  working_days: number
  max_lessons: number
  lessons_range: number[]
  class_hour_day: number | null
  class_hour_time_label: string | null
  lesson_times_by_day: Record<number, Record<number, string>>
  cells: ReportCell[]
}

export type TeacherReport = {
  teacher_id: number
  teacher_name: string
  day_names: string[]
  working_days: number
  max_lessons: number
  lessons_range: number[]
  class_hour_day: number | null
  class_hour_time_label: string | null
  lesson_times_by_day: Record<number, Record<number, string>>
  cells: ReportCell[]
}

export function fetchClassReport(classId: number) {
  return apiJson<ClassReport>(`/api/reports/class/${classId}`)
}

export function fetchTeacherReport(teacherId: number) {
  return apiJson<TeacherReport>(`/api/reports/teacher/${teacherId}`)
}

export function exportClassUrl(classId: number) {
  return `/api/reports/export/class/${classId}`
}

export function exportTeacherUrl(teacherId: number) {
  return `/api/reports/export/teacher/${teacherId}`
}

export function exportAllUrl(schoolLevel: 'elementary' | 'secondary') {
  return `/api/reports/export/all/${schoolLevel}`
}
