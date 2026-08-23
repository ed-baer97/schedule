import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { apiJson, extractApiError } from '../api/client'
import { ModalPortal } from '../components/ModalPortal'

type LessonTime = {
  id: number
  day_of_week: number
  lesson_number: number
  time_start: string
  time_end: string
}

type Shift = {
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

type BellRow = { time_start: string; time_end: string }
type BellState = { common: Record<string, BellRow>; class_day: Record<string, BellRow> }

const DAY_NAMES: Record<number, string> = {
  1: 'Понедельник',
  2: 'Вторник',
  3: 'Среда',
  4: 'Четверг',
  5: 'Пятница',
  6: 'Суббота',
}

const DEFAULT_LESSON_DURATION = 45
const DEFAULT_BREAK = 10
const DEFAULT_FIRST_START = '08:00'

const EMPTY_FORM = {
  name: '',
  school_level: 'elementary',
  start_lesson: '1',
  lessons_count: '6',
  working_days: '5',
  max_lessons_per_day: '7',
  class_hour_day: '',
  class_hour_start: DEFAULT_FIRST_START,
  class_hour_duration: String(DEFAULT_LESSON_DURATION),
  class_hour_break: String(DEFAULT_BREAK),
  first_lesson_start: DEFAULT_FIRST_START,
  lesson_duration: String(DEFAULT_LESSON_DURATION),
}

function parseHM(value: string): number | null {
  const m = /^(\d{1,2}):(\d{2})/.exec(value.trim())
  if (!m) return null
  const h = Number(m[1])
  const min = Number(m[2])
  if (h > 23 || min > 59) return null
  return h * 60 + min
}

function formatHM(total: number): string {
  const t = ((total % (24 * 60)) + 24 * 60) % (24 * 60)
  const h = Math.floor(t / 60)
  const m = t % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

function addMinutes(hhmm: string, minutes: number): string | null {
  const t = parseHM(hhmm)
  if (t == null) return null
  return formatHM(t + minutes)
}

function diffMinutes(start: string, end: string): number | null {
  const a = parseHM(start)
  const b = parseHM(end)
  if (a == null || b == null) return null
  return b - a
}

function fmtRange(start: string, end: string): string {
  if (!start || !end) return '—'
  return `${start}–${end}`
}

function lessonNumbers(start: number, count: number): number[] {
  const out: number[] = []
  for (let n = start; n < start + count; n += 1) out.push(n)
  return out
}

function toInt(value: string, fallback: number): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function padBreaks(start: number, count: number, existing: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  const nums = lessonNumbers(start, count)
  for (let i = 0; i < nums.length - 1; i += 1) {
    const key = String(nums[i])
    out[key] = existing[key] ?? String(DEFAULT_BREAK)
  }
  return out
}

function breaksAsNumbers(breaks: Record<string, string>): Record<string, number> {
  const out: Record<string, number> = {}
  for (const [k, v] of Object.entries(breaks)) {
    const n = Number(v)
    out[k] = Number.isFinite(n) && n >= 0 ? n : 0
  }
  return out
}

function buildLessonTimes(
  nums: number[],
  firstStart: string,
  duration: number,
  breaksAfter: Record<string, number>,
  insert: { start: string; duration: number; breakAfter: number } | null,
): Record<string, BellRow> {
  const start0 = parseHM(firstStart)
  if (start0 == null || duration < 1) {
    return Object.fromEntries(nums.map((n) => [String(n), { time_start: '', time_end: '' }]))
  }
  const insStart = insert ? parseHM(insert.start) : null
  const ins =
    insert && insStart != null && insert.duration >= 1
      ? { start: insStart, duration: insert.duration, breakAfter: Math.max(0, insert.breakAfter) }
      : null

  const out: Record<string, BellRow> = {}
  let t = start0
  let inserted = !ins
  if (ins && ins.start <= t) {
    t = ins.start + ins.duration + ins.breakAfter
    inserted = true
  }
  for (const n of nums) {
    if (!inserted && ins && ins.start <= t) {
      t = ins.start + ins.duration + ins.breakAfter
      inserted = true
    }
    out[String(n)] = { time_start: formatHM(t), time_end: formatHM(t + duration) }
    t = t + duration + (breaksAfter[String(n)] ?? 0)
  }
  return out
}

function computeBells(params: {
  startLesson: number
  lessonsCount: number
  firstLessonStart: string
  lessonDuration: number
  breaksAfter: Record<string, number>
  classHourDay: number | null
  classHourStart: string
  classHourDuration: number
  classHourBreak: number
}): { classHourEnd: string | null; common: Record<string, BellRow>; class_day: Record<string, BellRow> } {
  const nums = lessonNumbers(params.startLesson, params.lessonsCount)
  const common = buildLessonTimes(
    nums,
    params.firstLessonStart,
    params.lessonDuration,
    params.breaksAfter,
    null,
  )
  let classHourEnd: string | null = null
  let class_day: Record<string, BellRow> = {}
  if (params.classHourDay != null && params.classHourStart && params.classHourDuration >= 1) {
    classHourEnd = addMinutes(params.classHourStart, params.classHourDuration)
    class_day = buildLessonTimes(
      nums,
      params.firstLessonStart,
      params.lessonDuration,
      params.breaksAfter,
      {
        start: params.classHourStart,
        duration: params.classHourDuration,
        breakAfter: Math.max(0, params.classHourBreak),
      },
    )
  }
  return { classHourEnd, common, class_day }
}

function inferFromShift(s: Shift): { form: typeof EMPTY_FORM; breaksAfter: Record<string, string> } {
  const wd = s.working_days || 5
  const classDay = s.class_hour_day && s.class_hour_day <= wd ? s.class_hour_day : null
  const byDay: Record<number, Record<number, BellRow>> = {}
  for (const lt of s.lesson_times) {
    byDay[lt.day_of_week] ??= {}
    byDay[lt.day_of_week][lt.lesson_number] = { time_start: lt.time_start, time_end: lt.time_end }
  }
  const common: Record<string, BellRow> = {}
  const class_day: Record<string, BellRow> = {}
  const nums = lessonNumbers(s.start_lesson, s.lessons_count)
  for (const n of nums) {
    let chosen: BellRow | null = null
    for (let d = 1; d <= Math.min(wd, 6); d += 1) {
      if (classDay && d === classDay) continue
      const v = byDay[d]?.[n]
      if (v && (v.time_start || v.time_end)) {
        chosen = v
        break
      }
    }
    common[String(n)] = chosen ?? { time_start: '', time_end: '' }
    if (classDay) {
      const v = byDay[classDay]?.[n]
      class_day[String(n)] = v ?? { time_start: '', time_end: '' }
    }
  }

  const first = common[String(nums[0])]
  const firstStart = first?.time_start || DEFAULT_FIRST_START
  const rawDur = first?.time_start && first?.time_end ? diffMinutes(first.time_start, first.time_end) : null
  const duration = rawDur != null && rawDur > 0 ? rawDur : DEFAULT_LESSON_DURATION

  const breaksAfter: Record<string, string> = {}
  for (let i = 0; i < nums.length - 1; i += 1) {
    const a = common[String(nums[i])]
    const b = common[String(nums[i + 1])]
    const gap = a?.time_end && b?.time_start ? diffMinutes(a.time_end, b.time_start) : null
    breaksAfter[String(nums[i])] = String(gap != null && gap >= 0 ? gap : DEFAULT_BREAK)
  }

  let classHourDuration = DEFAULT_LESSON_DURATION
  let classHourBreak = DEFAULT_BREAK
  if (s.class_hour_start && s.class_hour_end) {
    const d = diffMinutes(s.class_hour_start, s.class_hour_end)
    if (d != null && d > 0) classHourDuration = d
    const chEnd = parseHM(s.class_hour_end)
    if (chEnd != null) {
      for (const n of nums) {
        const row = class_day[String(n)]
        const start = row?.time_start ? parseHM(row.time_start) : null
        if (start != null && start >= chEnd) {
          const gap = start - chEnd
          if (gap >= 0) classHourBreak = gap
          break
        }
      }
    }
  }

  return {
    form: {
      name: s.name,
      school_level: s.school_level,
      start_lesson: String(s.start_lesson),
      lessons_count: String(s.lessons_count),
      working_days: String(s.working_days),
      max_lessons_per_day: String(s.max_lessons_per_day),
      class_hour_day: classDay == null ? '' : String(classDay),
      class_hour_start: s.class_hour_start ?? DEFAULT_FIRST_START,
      class_hour_duration: String(classHourDuration),
      class_hour_break: String(classHourBreak),
      first_lesson_start: firstStart,
      lesson_duration: String(duration),
    },
    breaksAfter,
  }
}

export function ShiftsPage() {
  const qc = useQueryClient()
  const [msg, setMsg] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [breaksAfter, setBreaksAfter] = useState<Record<string, string>>(() => padBreaks(1, 6, {}))

  const q = useQuery({
    queryKey: ['shifts'],
    queryFn: () => apiJson<Shift[]>('/api/shifts/'),
  })

  const saveM = useMutation({
    mutationFn: async () => {
      const startLesson = Math.max(1, toInt(form.start_lesson, 1))
      const lessonsCount = Math.max(1, toInt(form.lessons_count, 6))
      const lessonDuration = toInt(form.lesson_duration, 0)
      const classHourDay = form.class_hour_day === '' ? null : Number(form.class_hour_day)
      const classHourDuration = toInt(form.class_hour_duration, 0)
      const classHourBreak = toInt(form.class_hour_break, 0)

      if (!form.name.trim()) throw new Error('Укажите название смены')
      if (parseHM(form.first_lesson_start) == null) {
        throw new Error('Укажите начало первого урока')
      }
      if (lessonDuration < 1) throw new Error('Укажите продолжительность урока')
      if (classHourDay != null) {
        if (parseHM(form.class_hour_start) == null) {
          throw new Error('Укажите начало классного часа')
        }
        if (classHourDuration < 1) throw new Error('Укажите продолжительность классного часа')
      }

      const computed = computeBells({
        startLesson,
        lessonsCount,
        firstLessonStart: form.first_lesson_start,
        lessonDuration,
        breaksAfter: breaksAsNumbers(breaksAfter),
        classHourDay,
        classHourStart: form.class_hour_start,
        classHourDuration,
        classHourBreak,
      })

      const base = {
        name: form.name.trim(),
        school_level: form.school_level,
        start_lesson: startLesson,
        lessons_count: lessonsCount,
        working_days: toInt(form.working_days, 5),
        max_lessons_per_day: toInt(form.max_lessons_per_day, 7),
        class_hour_day: classHourDay,
        class_hour_start: classHourDay != null ? form.class_hour_start : null,
        class_hour_end: classHourDay != null ? computed.classHourEnd : null,
      }

      let shiftId: number
      if (editingId === 'new') {
        const created = await apiJson<{ id: number }>('/api/shifts/', {
          method: 'POST',
          body: JSON.stringify(base),
        })
        shiftId = created.id
      } else if (typeof editingId === 'number') {
        await apiJson(`/api/shifts/${editingId}`, { method: 'PUT', body: JSON.stringify(base) })
        shiftId = editingId
      } else {
        throw new Error('Не выбрана смена')
      }

      const bell: BellState = { common: computed.common, class_day: computed.class_day }
      const applied = await apiJson<{ inserted: number; warnings: string[] }>(
        `/api/shifts/${shiftId}/lesson-times`,
        { method: 'PUT', body: JSON.stringify(bell) },
      )
      return applied
    },
    onSuccess: async (res) => {
      const warns = res.warnings?.length ? ` Предупреждения: ${res.warnings.join('; ')}` : ''
      setMsg(`Сохранено. Звонков добавлено: ${res.inserted}.${warns}`)
      setEditingId(null)
      await qc.invalidateQueries({ queryKey: ['shifts'] })
    },
  })

  const delM = useMutation({
    mutationFn: (id: number) => apiJson<void>(`/api/shifts/${id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      setMsg('Удалено')
      await qc.invalidateQueries({ queryKey: ['shifts'] })
    },
    onError: (e) => setMsg(extractApiError(e)),
  })

  useEffect(() => {
    if (!msg) return
    const t = setTimeout(() => setMsg(null), 5000)
    return () => clearTimeout(t)
  }, [msg])

  function openNew() {
    saveM.reset()
    setForm(EMPTY_FORM)
    setBreaksAfter(padBreaks(1, 6, {}))
    setEditingId('new')
  }

  function openEdit(s: Shift) {
    saveM.reset()
    const inferred = inferFromShift(s)
    setForm(inferred.form)
    setBreaksAfter(inferred.breaksAfter)
    setEditingId(s.id)
  }

  if (q.isLoading) return <p>Загрузка…</p>
  if (q.isError) return <p className="text-danger">{(q.error as Error).message}</p>
  const rows = q.data ?? []

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h1 className="h3 mb-0">Смены</h1>
        <button type="button" className="btn btn-primary" onClick={openNew}>
          Добавить
        </button>
      </div>
      {msg && <div className="alert alert-info py-2">{msg}</div>}
      <div className="table-responsive card shadow-sm">
        <table className="table table-hover mb-0">
          <thead className="table-light">
            <tr>
              <th>Название</th>
              <th>Уровень</th>
              <th>Уроки</th>
              <th>Дней</th>
              <th>Звонков</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id}>
                <td>{s.name}</td>
                <td>{s.school_level_display}</td>
                <td>
                  {s.start_lesson}…{s.start_lesson + s.lessons_count - 1}
                </td>
                <td>{s.working_days}</td>
                <td>{s.lesson_times.length}</td>
                <td className="text-end text-nowrap">
                  <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => openEdit(s)}>
                    Изменить
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-danger"
                    onClick={() => {
                      if (confirm(`Удалить смену «${s.name}»?`)) delM.mutate(s.id)
                    }}
                  >
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editingId !== null && (
        <ShiftEditor
          form={form}
          setForm={setForm}
          breaksAfter={breaksAfter}
          setBreaksAfter={setBreaksAfter}
          saving={saveM.isPending}
          error={saveM.isError ? extractApiError(saveM.error) : null}
          onCancel={() => {
            saveM.reset()
            setEditingId(null)
          }}
          onSave={() => saveM.mutate()}
          isNew={editingId === 'new'}
        />
      )}
    </div>
  )
}

type EditorProps = {
  form: typeof EMPTY_FORM
  setForm: React.Dispatch<React.SetStateAction<typeof EMPTY_FORM>>
  breaksAfter: Record<string, string>
  setBreaksAfter: React.Dispatch<React.SetStateAction<Record<string, string>>>
  saving: boolean
  error: string | null
  onCancel: () => void
  onSave: () => void
  isNew: boolean
}

function ShiftEditor({
  form,
  setForm,
  breaksAfter,
  setBreaksAfter,
  saving,
  error,
  onCancel,
  onSave,
  isNew,
}: EditorProps) {
  const startLesson = Math.max(1, toInt(form.start_lesson, 1))
  const lessonsCount = Math.max(1, toInt(form.lessons_count, 1))
  const workingDays = Math.max(5, Math.min(6, toInt(form.working_days, 5)))
  const classHourDay = form.class_hour_day === '' ? null : Number(form.class_hour_day)
  const hasClassDay = classHourDay !== null && classHourDay >= 1 && classHourDay <= workingDays
  const lessonDuration = toInt(form.lesson_duration, 0)
  const classHourDuration = toInt(form.class_hour_duration, 0)
  const classHourBreak = toInt(form.class_hour_break, 0)

  const nums = useMemo(() => lessonNumbers(startLesson, lessonsCount), [startLesson, lessonsCount])

  const computed = useMemo(
    () =>
      computeBells({
        startLesson,
        lessonsCount,
        firstLessonStart: form.first_lesson_start,
        lessonDuration,
        breaksAfter: breaksAsNumbers(breaksAfter),
        classHourDay: hasClassDay ? classHourDay : null,
        classHourStart: form.class_hour_start,
        classHourDuration,
        classHourBreak,
      }),
    [
      startLesson,
      lessonsCount,
      form.first_lesson_start,
      form.class_hour_start,
      lessonDuration,
      breaksAfter,
      hasClassDay,
      classHourDay,
      classHourDuration,
      classHourBreak,
    ],
  )

  function changeGrid(patch: Partial<typeof EMPTY_FORM>) {
    const next = { ...form, ...patch }
    const start = Math.max(1, toInt(next.start_lesson, 1))
    const count = Math.max(1, toInt(next.lessons_count, 1))
    setForm(next)
    setBreaksAfter((prev) => padBreaks(start, count, prev))
  }

  function setBreak(n: number, value: string) {
    setBreaksAfter((prev) => ({ ...prev, [String(n)]: value }))
  }

  const classHourEndLabel =
    hasClassDay && computed.classHourEnd
      ? fmtRange(form.class_hour_start, computed.classHourEnd)
      : null

  return (
    <ModalPortal>
      <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,.35)' }}>
        <div className="modal-dialog modal-xl modal-dialog-centered modal-dialog-scrollable">
          <div className="modal-content">
            <div className="modal-header">
              <h5 className="modal-title">{isNew ? 'Новая смена' : 'Редактирование смены'}</h5>
              <button type="button" className="btn-close" onClick={onCancel} aria-label="Закрыть" />
            </div>
            <div className="modal-body row g-2">
              <div className="col-md-6">
                <label className="form-label">Название</label>
                <input
                  className={`form-control${error && !form.name.trim() ? ' is-invalid' : ''}`}
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                />
                {error && !form.name.trim() && (
                  <div className="invalid-feedback">Укажите название смены</div>
                )}
              </div>
              <div className="col-md-6">
                <label className="form-label">Уровень</label>
                <select
                  className="form-select"
                  value={form.school_level}
                  onChange={(e) => setForm((f) => ({ ...f, school_level: e.target.value }))}
                >
                  <option value="elementary">Начальная школа</option>
                  <option value="secondary">Основная школа</option>
                </select>
              </div>
              <div className="col-md-3">
                <label className="form-label">С какого урока</label>
                <input
                  className="form-control"
                  type="number"
                  min={1}
                  max={10}
                  value={form.start_lesson}
                  onChange={(e) => changeGrid({ start_lesson: e.target.value })}
                />
              </div>
              <div className="col-md-3">
                <label className="form-label">Кол-во уроков</label>
                <input
                  className="form-control"
                  type="number"
                  min={1}
                  max={10}
                  value={form.lessons_count}
                  onChange={(e) => changeGrid({ lessons_count: e.target.value })}
                />
              </div>
              <div className="col-md-3">
                <label className="form-label">Дней в неделе</label>
                <select
                  className="form-select"
                  value={form.working_days}
                  onChange={(e) => setForm((f) => ({ ...f, working_days: e.target.value }))}
                >
                  <option value="5">5</option>
                  <option value="6">6</option>
                </select>
              </div>
              <div className="col-md-3">
                <label className="form-label">Макс. уроков в сетке</label>
                <input
                  className="form-control"
                  type="number"
                  min={1}
                  max={10}
                  value={form.max_lessons_per_day}
                  onChange={(e) => setForm((f) => ({ ...f, max_lessons_per_day: e.target.value }))}
                />
              </div>

              <div className="col-12">
                <hr />
                <div className="small text-muted mb-2">Классный час (необязательно)</div>
              </div>
              <div className="col-md-3">
                <label className="form-label">День</label>
                <select
                  className="form-select"
                  value={form.class_hour_day}
                  onChange={(e) => setForm((f) => ({ ...f, class_hour_day: e.target.value }))}
                >
                  <option value="">— не задан —</option>
                  {Array.from({ length: workingDays }, (_, i) => i + 1).map((d) => (
                    <option key={d} value={d}>
                      {DAY_NAMES[d]}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-md-3">
                <label className="form-label">Начало</label>
                <input
                  className="form-control"
                  type="time"
                  step={60}
                  value={form.class_hour_start}
                  onChange={(e) => setForm((f) => ({ ...f, class_hour_start: e.target.value }))}
                />
              </div>
              <div className="col-md-3">
                <label className="form-label">Продолжительность, мин</label>
                <input
                  className="form-control"
                  type="number"
                  min={5}
                  max={90}
                  step={5}
                  value={form.class_hour_duration}
                  onChange={(e) => setForm((f) => ({ ...f, class_hour_duration: e.target.value }))}
                />
              </div>
              <div className="col-md-3">
                <label className="form-label">Перемена после, мин</label>
                <input
                  className="form-control"
                  type="number"
                  min={0}
                  max={60}
                  step={5}
                  value={form.class_hour_break}
                  onChange={(e) => setForm((f) => ({ ...f, class_hour_break: e.target.value }))}
                />
              </div>
              {classHourEndLabel && (
                <div className="col-12">
                  <div className="small text-muted">
                    Классный час: {classHourEndLabel}
                    {classHourBreak >= 0 ? `, затем перемена ${classHourBreak} мин` : ''}
                  </div>
                </div>
              )}

              <div className="col-12 mt-2">
                <hr />
                <div className="d-flex justify-content-between align-items-center mb-2">
                  <h6 className="mb-0">Расписание звонков</h6>
                  <span className="small text-muted">Начало и конец уроков считаются автоматически</span>
                </div>
              </div>
              <div className="col-md-6">
                <label className="form-label">Начало {startLesson}-го урока</label>
                <input
                  className="form-control"
                  type="time"
                  step={60}
                  value={form.first_lesson_start}
                  onChange={(e) => setForm((f) => ({ ...f, first_lesson_start: e.target.value }))}
                />
              </div>
              <div className="col-md-6">
                <label className="form-label">Продолжительность урока, мин</label>
                <input
                  className="form-control"
                  type="number"
                  min={15}
                  max={90}
                  step={5}
                  value={form.lesson_duration}
                  onChange={(e) => setForm((f) => ({ ...f, lesson_duration: e.target.value }))}
                />
              </div>
              <div className="col-12">
                <div className="table-responsive">
                  <table className="table table-sm align-middle mb-0">
                    <thead className="table-light">
                      <tr>
                        <th style={{ width: 70 }}>Урок</th>
                        <th style={{ width: 160 }}>Перемена после, мин</th>
                        <th>{hasClassDay ? 'Остальные дни' : 'Все дни'}</th>
                        {hasClassDay && <th>День «{DAY_NAMES[classHourDay!]}»</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {hasClassDay && computed.classHourEnd && (
                        <tr className="table-warning">
                          <td className="fw-semibold">КЧ</td>
                          <td className="text-muted">{classHourBreak}</td>
                          <td className="text-muted">—</td>
                          <td className="text-nowrap fw-semibold">
                            {fmtRange(form.class_hour_start, computed.classHourEnd)}
                          </td>
                        </tr>
                      )}
                      {nums.map((n, idx) => {
                        const c = computed.common[String(n)] ?? { time_start: '', time_end: '' }
                        const k = computed.class_day[String(n)] ?? { time_start: '', time_end: '' }
                        const isLast = idx === nums.length - 1
                        return (
                          <tr key={n}>
                            <td className="fw-semibold">{n}</td>
                            <td>
                              {isLast ? (
                                <span className="text-muted">—</span>
                              ) : (
                                <input
                                  className="form-control form-control-sm"
                                  type="number"
                                  min={0}
                                  max={60}
                                  step={5}
                                  value={breaksAfter[String(n)] ?? ''}
                                  onChange={(e) => setBreak(n, e.target.value)}
                                />
                              )}
                            </td>
                            <td className="text-nowrap">{fmtRange(c.time_start, c.time_end)}</td>
                            {hasClassDay && (
                              <td className="text-nowrap">{fmtRange(k.time_start, k.time_end)}</td>
                            )}
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <div className="modal-footer flex-wrap gap-2">
              {error && (
                <div className="alert alert-danger py-2 mb-0 me-auto" style={{ whiteSpace: 'pre-line' }}>
                  Не удалось сохранить: {error}
                </div>
              )}
              <button type="button" className="btn btn-secondary" onClick={onCancel}>
                Отмена
              </button>
              <button type="button" className="btn btn-primary" disabled={saving} onClick={onSave}>
                {saving ? 'Сохранение…' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </ModalPortal>
  )
}
