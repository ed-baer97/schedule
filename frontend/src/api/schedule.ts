import { apiJson, extractApiError, ApiError } from './client'
import type { ShiftBrief } from './shifts'
import type { SchoolLevel } from '../domain/schoolLevel'

export type ClassroomMode = 'class_room' | 'teacher_room'

export type ScheduleSettings = {
  school_level: string
  max_lessons_per_subject_per_day: number
  classroom_mode: ClassroomMode
  elementary_group_subjects_leave: boolean
  pref_teacher_gaps: number
  pref_hard_subjects_early: number
  pref_adjacent_pairs: number
  pref_classroom_stability: number
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
  requires_fixed_classroom?: boolean
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
  class_hour_lessons_count: number | null
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

export type ClassroomChoice = {
  id: number
  number: string
  name: string | null
  display_name: string
  subject_ids: number[]
  is_exclusive: boolean
  school_level?: string | null
  classes_capacity?: number | null
  subgroup_only?: boolean
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
  requires_fixed_classroom?: boolean
}

export type AssignmentsData = {
  assignments: AssignmentChoice[]
  classrooms: ClassroomChoice[]
}

export type ScheduleWarning = ClassroomWarning

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
  class_id?: number
  classroom_id?: number | null
  set_classroom?: boolean
}

export type ClearScheduleFilter = {
  school_level?: string
  class_id?: number
  teacher_id?: number
  days_of_week?: number[]
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

export function swapScheduleClassrooms(cellId: number, otherCellId: number) {
  return apiJson<{ cell: ScheduleCell; other: ScheduleCell }>(
    `/api/schedule/cells/${cellId}/swap-classroom`,
    {
      method: 'POST',
      body: JSON.stringify({ other_cell_id: otherCellId }),
    },
  )
}

export function fetchAssignmentsForClass(
  classId: number,
  slot?: { day: number; lesson: number },
) {
  const q =
    slot != null
      ? `?day_of_week=${slot.day}&lesson_number=${slot.lesson}`
      : ''
  return apiJson<AssignmentsData>(`/api/schedule/assignments-for-class/${classId}${q}`)
}

export type TeacherDayOccupant = {
  class_id: number
  class_name: string
  subject_name: string
  subject_color: string
  classroom_name: string | null
  group_number: number | null
}

export type TeacherDayLesson = {
  lesson: number
  time_label: string | null
  is_candidate: boolean
  is_gap: boolean
  overlaps_current: boolean
  occupants: TeacherDayOccupant[]
}

export type TeacherDayShift = {
  shift_id: number | null
  shift_name: string
  is_current: boolean
  lessons: TeacherDayLesson[]
}

export type TeacherDayData = {
  teacher_id: number
  teacher_name: string
  day_of_week: number
  day_name: string
  other_shift_gap: string | null
  shifts: TeacherDayShift[]
}

export function fetchTeacherDay(params: {
  teacherId: number
  day: number
  classId?: number
  lesson?: number
}) {
  const q = new URLSearchParams()
  q.set('teacher_id', String(params.teacherId))
  q.set('day_of_week', String(params.day))
  if (params.classId != null) q.set('class_id', String(params.classId))
  if (params.lesson != null) q.set('lesson_number', String(params.lesson))
  return apiJson<TeacherDayData>(`/api/schedule/teacher-day?${q.toString()}`)
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

export function fetchActiveJob() {
  return apiJson<{ job: JobOut | null }>('/api/jobs/active').then((r) => r.job)
}

export function cancelJob(jobId: number, force = false) {
  const q = force ? '?force=true' : ''
  return apiJson<JobOut>(`/api/jobs/${jobId}/cancel${q}`, { method: 'POST' })
}

/** Parse «задача #N» from a 409 conflict body. */
export function stuckJobIdFromError(err: unknown): number | null {
  if (err instanceof ApiError) {
    try {
      const data = JSON.parse(err.body) as { detail?: unknown }
      const detail = data.detail
      if (detail && typeof detail === 'object') {
        const id = (detail as { job_id?: unknown }).job_id
        if (typeof id === 'number' && Number.isFinite(id)) return id
      }
    } catch {
      /* not JSON */
    }
  }
  const msg = extractApiError(err)
  const m = msg.match(/задача #(\d+)/i)
  if (!m) return null
  const id = Number(m[1])
  return Number.isFinite(id) ? id : null
}

export type AutoAllPayload = {
  school_level: SchoolLevel
  shift_id: number
  time_limit_sec: number
  random_seed: number
  diagnose: boolean
  split?: 'shift' | 'grade_bands'
  hours_first?: 'more' | 'fewer'
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

export type ExplainSlotPayload = {
  assignment_id: number
  day_of_week: number
  lesson_number: number
  classroom_id?: number | null
  cell_id?: number | null
}

export type ExplainSlotOut = {
  allowed: boolean
  blockers: string[]
  alternatives: {
    day_of_week: number
    lesson_number: number
    day_name: string
    label: string
  }[]
  text: string
  llm_used: boolean
}

export function explainSlot(payload: ExplainSlotPayload) {
  return apiJson<ExplainSlotOut>('/api/schedule/explain', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export type AssistPayload = {
  message: string
  school_level: SchoolLevel
  shift_id?: number | null
  apply?: boolean
}

export type AssistMove = {
  cell_id: number
  subject: string
  class_name: string
  from_day: number
  from_lesson: number
  to_day: number
  to_lesson: number
  allowed: boolean
  applied: boolean
  blockers: string[]
  label: string
}

export type AssistOut = {
  interpretation: string
  llm_used: boolean
  preference_updates: Record<string, number>
  preferences_applied: boolean
  moves: AssistMove[]
  applied_moves: number
  rejected: AssistMove[]
}

export function assistSchedule(payload: AssistPayload) {
  return apiJson<AssistOut>('/api/schedule/assist', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export type RepairPayload = {
  school_level: SchoolLevel
  teacher_id?: number | null
  class_id?: number | null
}

export function enqueueRepair(payload: RepairPayload) {
  return apiJson<{ job_id: number }>('/api/schedule/repair', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export class JobPollAborted extends Error {
  constructor() {
    super('aborted')
    this.name = 'JobPollAborted'
  }
}

function throwIfAborted(signal?: AbortSignal) {
  if (signal?.aborted) throw new JobPollAborted()
}

export async function pollJob(
  jobId: number,
  onProgress: (p: { current: number; total: number; message: string }) => void,
  onLog: (line: string) => void,
  signal?: AbortSignal,
): Promise<JobOut> {
  let lastLogged = ''
  for (;;) {
    throwIfAborted(signal)
    const job = await getJob(jobId)
    throwIfAborted(signal)
    const prog = job.progress || {}
    const message = String(prog.message || '')
    onProgress({
      current: Number(prog.current || 0),
      total: Number(prog.total || 0),
      message: message || job.status,
    })
    if (message && message !== lastLogged) {
      lastLogged = message
      onLog(message)
    }
    if (
      job.status === 'done' ||
      job.status === 'failed' ||
      job.status === 'cancelled'
    ) {
      return job
    }
    await new Promise<void>((resolve, reject) => {
      const onAbort = () => {
        window.clearTimeout(t)
        reject(new JobPollAborted())
      }
      const t = window.setTimeout(() => {
        signal?.removeEventListener('abort', onAbort)
        resolve()
      }, 1000)
      if (!signal) return
      if (signal.aborted) {
        window.clearTimeout(t)
        reject(new JobPollAborted())
        return
      }
      signal.addEventListener('abort', onAbort, { once: true })
    })
  }
}

export async function runJobAndPoll(
  start: () => Promise<{ job_id: number }>,
  onProgress: (p: { current: number; total: number; message: string }) => void,
  onLog: (line: string) => void,
  onStarted?: (jobId: number) => void,
  signal?: AbortSignal,
): Promise<JobOut> {
  const started = await start()
  onStarted?.(started.job_id)
  onLog(`Задача #${started.job_id} поставлена в очередь`)
  return pollJob(started.job_id, onProgress, onLog, signal)
}
