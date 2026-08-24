import { apiJson } from './client'
import type { ShiftBrief } from './shifts'
import type { SchoolLevel } from '../domain/schoolLevel'

export type ClassroomMode = 'class_room' | 'teacher_room'

export type ScheduleSettings = {
  school_level: string
  max_lessons_per_subject_per_day: number
  classroom_mode: ClassroomMode
  elementary_group_subjects_leave: boolean
}

export type ClassroomWarning = { type: string; message: string }

export type ScheduleCell = {
  id: number
  class_id: number
  day_of_week: number
  lesson_number: number
  assignment_id: number
  classroom_id: number | null
  subject_id: number
  subject_name: string
  subject_color: string
  teacher_id: number | null
  teacher_name: string | null
  group_number: number | null
  classroom_name: string | null
}

export type SchoolClassRow = {
  id: number
  name: string
  grade: number
  school_level: string
  shift_id: number | null
}

export type ShiftBriefWithClassHour = ShiftBrief & {
  class_hour_day: number | null
  class_hour_time_label: string | null
}

export type GridData = {
  school_level: SchoolLevel
  current_shift_id: number | null
  current_shift: ShiftBriefWithClassHour | null
  shifts: ShiftBriefWithClassHour[]
  classes: SchoolClassRow[]
  day_names: string[]
  working_days: number
  max_lessons: number
  lessons_range: number[]
  lesson_times_by_day: Record<number, Record<number, string>>
  class_hour_time_label: string
  cells: ScheduleCell[]
  classroom_warnings: ClassroomWarning[]
  settings: ScheduleSettings | null
}

export type AssignmentChoice = {
  id: number
  subject_id: number
  subject_name: string
  subject_color: string
  teacher_id: number | null
  teacher_name: string | null
  group_number: number | null
  remaining_hours: number
  preferred_classroom_id: number | null
}

export type ClassroomChoice = {
  id: number
  number: string
  name: string | null
  display_name: string
}

export type AssignmentsData = {
  assignments: AssignmentChoice[]
  classrooms: ClassroomChoice[]
}

export type ScheduleWarning = { type: string; message: string }

export type AutoPageData = {
  teachers: { id: number; full_name: string }[]
  classes: { id: number; name: string; school_level: string }[]
  elementary_warnings: ScheduleWarning[]
  secondary_warnings: ScheduleWarning[]
  elementary_settings: ScheduleSettings | null
  secondary_settings: ScheduleSettings | null
  shifts_elementary: ShiftBrief[]
  shifts_secondary: ShiftBrief[]
}

export type JobOut = {
  id: number
  kind: string
  status: string
  progress: { current?: number; total?: number; message?: string } | null
  result: { type?: string; count?: number; message?: string; [k: string]: unknown } | null
  error: string | null
}

export type CreateCellPayload = {
  class_id: number
  day_of_week: number
  lesson_number: number
  assignment_id: number
  classroom_id: number | null
}

export type MoveCellPayload = {
  day_of_week: number
  lesson_number: number
  class_id: number
}

export type ClearScheduleFilter = {
  school_level?: string
  class_id?: number
  teacher_id?: number
}

export function fetchGrid(schoolLevel: SchoolLevel, shiftId?: number | null) {
  const qs = shiftId ? `&shift_id=${shiftId}` : ''
  return apiJson<GridData>(`/api/schedule/grid?school_level=${schoolLevel}${qs}`)
}

export function createScheduleCell(payload: CreateCellPayload) {
  return apiJson<ScheduleCell>('/api/schedule/cells', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateScheduleCell(cellId: number, payload: MoveCellPayload) {
  return apiJson<ScheduleCell>(`/api/schedule/cells/${cellId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteScheduleCell(cellId: number) {
  return apiJson<void>(`/api/schedule/cells/${cellId}`, { method: 'DELETE' })
}

export function fetchAssignmentsForClass(classId: number) {
  return apiJson<AssignmentsData>(`/api/schedule/assignments-for-class/${classId}`)
}

export function fetchAutoPageData() {
  return apiJson<AutoPageData>('/api/schedule/auto/page-data')
}

export function updateScheduleSettings(level: SchoolLevel, payload: Partial<ScheduleSettings>) {
  return apiJson<ScheduleSettings>(`/api/schedule/settings/${level}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function clearSchedule(filter: ClearScheduleFilter) {
  return apiJson<{ count: number }>('/api/schedule/clear', {
    method: 'POST',
    body: JSON.stringify(filter),
  })
}

export function getJob(jobId: number) {
  return apiJson<JobOut>(`/api/jobs/${jobId}`)
}

export type AutoAllPayload = {
  school_level: SchoolLevel
  solver: 'legacy' | 'cp_sat_mvp'
  shift_id: number | null
  time_limit_sec: number
  random_seed: number
  diagnose: boolean
}

export type AutoByTeacherPayload = {
  teacher_id: number
  school_level: SchoolLevel
  diagnose: boolean
}

export function enqueueAutoAll(payload: AutoAllPayload) {
  return apiJson<{ job_id: number }>('/api/schedule/auto', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function enqueueAutoByTeacher(payload: AutoByTeacherPayload) {
  return apiJson<{ job_id: number }>('/api/schedule/auto/by-teacher', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function runJobAndPoll(
  start: () => Promise<{ job_id: number }>,
  onProgress: (p: { current: number; total: number; message: string }) => void,
  onLog: (line: string) => void,
): Promise<JobOut> {
  const started = await start()
  onLog(`Задача #${started.job_id} поставлена в очередь`)
  for (;;) {
    await new Promise((r) => setTimeout(r, 1000))
    const job = await getJob(started.job_id)
    const prog = job.progress || {}
    onProgress({
      current: Number(prog.current || 0),
      total: Number(prog.total || 0),
      message: String(prog.message || job.status),
    })
    if (prog.message) {
      onLog(`[${prog.current ?? 0}/${prog.total ?? 0}] ${prog.message}`)
    }
    if (job.status === 'done' || job.status === 'failed') {
      return job
    }
  }
}
