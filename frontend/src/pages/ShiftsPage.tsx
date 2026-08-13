import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { apiJson } from '../api/client'

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

const EMPTY_FORM = {
  name: '',
  school_level: 'elementary',
  start_lesson: '1',
  lessons_count: '6',
  working_days: '5',
  max_lessons_per_day: '7',
  class_hour_day: '',
  class_hour_start: '',
  class_hour_end: '',
}

function emptyBell(): BellState {
  return { common: {}, class_day: {} }
}

function bellFromShift(s: Shift): BellState {
  const wd = s.working_days || 5
  const classDay = s.class_hour_day && s.class_hour_day <= wd ? s.class_hour_day : null
  const byDay: Record<number, Record<number, BellRow>> = {}
  for (const lt of s.lesson_times) {
    byDay[lt.day_of_week] ??= {}
    byDay[lt.day_of_week][lt.lesson_number] = { time_start: lt.time_start, time_end: lt.time_end }
  }
  const common: Record<string, BellRow> = {}
  const class_day: Record<string, BellRow> = {}
  for (let n = s.start_lesson; n < s.start_lesson + s.lessons_count; n += 1) {
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
  return { common, class_day }
}

export function ShiftsPage() {
  const qc = useQueryClient()
  const [msg, setMsg] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [bell, setBell] = useState<BellState>(emptyBell())

  const q = useQuery({
    queryKey: ['shifts'],
    queryFn: () => apiJson<Shift[]>('/api/shifts/'),
  })

  const saveM = useMutation({
    mutationFn: async () => {
      const base = {
        name: form.name.trim(),
        school_level: form.school_level,
        start_lesson: Number(form.start_lesson || 1),
        lessons_count: Number(form.lessons_count || 6),
        working_days: Number(form.working_days || 5),
        max_lessons_per_day: Number(form.max_lessons_per_day || 7),
        class_hour_day: form.class_hour_day === '' ? null : Number(form.class_hour_day),
        class_hour_start: form.class_hour_start.trim() || null,
        class_hour_end: form.class_hour_end.trim() || null,
      }
      if (!base.name) throw new Error('Укажите название смены')

      let shiftId: number
      if (editingId === 'new') {
        const created = await apiJson<{ id: number }>('/api/shifts/', { method: 'POST', body: JSON.stringify(base) })
        shiftId = created.id
      } else if (typeof editingId === 'number') {
        await apiJson(`/api/shifts/${editingId}`, { method: 'PUT', body: JSON.stringify(base) })
        shiftId = editingId
      } else {
        throw new Error('Не выбрана смена')
      }

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
    onError: (e: Error) => setMsg(e.message),
  })

  const delM = useMutation({
    mutationFn: (id: number) => apiJson<void>(`/api/shifts/${id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      setMsg('Удалено')
      await qc.invalidateQueries({ queryKey: ['shifts'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  useEffect(() => {
    if (!msg) return
    const t = setTimeout(() => setMsg(null), 5000)
    return () => clearTimeout(t)
  }, [msg])

  function openNew() {
    setForm(EMPTY_FORM)
    setBell(emptyBell())
    setEditingId('new')
  }

  function openEdit(s: Shift) {
    setForm({
      name: s.name,
      school_level: s.school_level,
      start_lesson: String(s.start_lesson),
      lessons_count: String(s.lessons_count),
      working_days: String(s.working_days),
      max_lessons_per_day: String(s.max_lessons_per_day),
      class_hour_day: s.class_hour_day === null ? '' : String(s.class_hour_day),
      class_hour_start: s.class_hour_start ?? '',
      class_hour_end: s.class_hour_end ?? '',
    })
    setBell(bellFromShift(s))
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
          bell={bell}
          setBell={setBell}
          saving={saveM.isPending}
          onCancel={() => setEditingId(null)}
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
  bell: BellState
  setBell: React.Dispatch<React.SetStateAction<BellState>>
  saving: boolean
  onCancel: () => void
  onSave: () => void
  isNew: boolean
}

function ShiftEditor({ form, setForm, bell, setBell, saving, onCancel, onSave, isNew }: EditorProps) {
  const startLesson = Math.max(1, Number(form.start_lesson || 1))
  const lessonsCount = Math.max(1, Number(form.lessons_count || 1))
  const workingDays = Math.max(5, Math.min(6, Number(form.working_days || 5)))
  const classHourDay = form.class_hour_day === '' ? null : Number(form.class_hour_day)
  const hasClassDay = classHourDay !== null && classHourDay >= 1 && classHourDay <= workingDays

  const lessonNumbers = useMemo(() => {
    const out: number[] = []
    for (let n = startLesson; n < startLesson + lessonsCount; n += 1) out.push(n)
    return out
  }, [startLesson, lessonsCount])

  function updateBell(table: 'common' | 'class_day', n: number, field: 'time_start' | 'time_end', value: string) {
    setBell((prev) => {
      const next = { ...prev, [table]: { ...prev[table] } }
      const key = String(n)
      const row = { ...(next[table][key] ?? { time_start: '', time_end: '' }) }
      row[field] = value
      next[table][key] = row
      return next
    })
  }

  return (
    <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,.35)' }}>
      <div className="modal-dialog modal-xl">
        <div className="modal-content">
          <div className="modal-header">
            <h5 className="modal-title">{isNew ? 'Новая смена' : 'Редактирование смены'}</h5>
            <button type="button" className="btn-close" onClick={onCancel} aria-label="Закрыть" />
          </div>
          <div className="modal-body row g-2">
            <div className="col-md-6">
              <label className="form-label">Название</label>
              <input className="form-control" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
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
              <input className="form-control" type="number" min={1} max={10} value={form.start_lesson} onChange={(e) => setForm((f) => ({ ...f, start_lesson: e.target.value }))} />
            </div>
            <div className="col-md-3">
              <label className="form-label">Кол-во уроков</label>
              <input className="form-control" type="number" min={1} max={10} value={form.lessons_count} onChange={(e) => setForm((f) => ({ ...f, lessons_count: e.target.value }))} />
            </div>
            <div className="col-md-3">
              <label className="form-label">Дней в неделе</label>
              <select className="form-select" value={form.working_days} onChange={(e) => setForm((f) => ({ ...f, working_days: e.target.value }))}>
                <option value="5">5</option>
                <option value="6">6</option>
              </select>
            </div>
            <div className="col-md-3">
              <label className="form-label">Макс. уроков в сетке</label>
              <input className="form-control" type="number" min={1} max={10} value={form.max_lessons_per_day} onChange={(e) => setForm((f) => ({ ...f, max_lessons_per_day: e.target.value }))} />
            </div>
            <div className="col-12">
              <hr />
              <div className="small text-muted mb-2">Классный час (необязательно)</div>
            </div>
            <div className="col-md-4">
              <label className="form-label">День</label>
              <select className="form-select" value={form.class_hour_day} onChange={(e) => setForm((f) => ({ ...f, class_hour_day: e.target.value }))}>
                <option value="">— не задан —</option>
                {Array.from({ length: workingDays }, (_, i) => i + 1).map((d) => (
                  <option key={d} value={d}>
                    {DAY_NAMES[d]}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-4">
              <label className="form-label">Начало HH:MM</label>
              <input className="form-control" placeholder="08:30" value={form.class_hour_start} onChange={(e) => setForm((f) => ({ ...f, class_hour_start: e.target.value }))} />
            </div>
            <div className="col-md-4">
              <label className="form-label">Конец HH:MM</label>
              <input className="form-control" placeholder="09:15" value={form.class_hour_end} onChange={(e) => setForm((f) => ({ ...f, class_hour_end: e.target.value }))} />
            </div>

            <div className="col-12 mt-3">
              <hr />
              <div className="d-flex justify-content-between align-items-center mb-2">
                <h6 className="mb-0">Расписание звонков</h6>
                <span className="small text-muted">Формат HH:MM. Пустая строка — без звонка.</span>
              </div>
              <div className="table-responsive">
                <table className="table table-sm align-middle mb-0">
                  <thead className="table-light">
                    <tr>
                      <th style={{ width: 80 }}>Урок</th>
                      <th colSpan={2}>{hasClassDay ? 'Остальные дни' : 'Все дни'}</th>
                      {hasClassDay && (
                        <th colSpan={2}>День «{DAY_NAMES[classHourDay!]}» (с классным часом)</th>
                      )}
                    </tr>
                    <tr>
                      <th />
                      <th>Начало</th>
                      <th>Конец</th>
                      {hasClassDay && (
                        <>
                          <th>Начало</th>
                          <th>Конец</th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {lessonNumbers.map((n) => {
                      const c = bell.common[String(n)] ?? { time_start: '', time_end: '' }
                      const k = bell.class_day[String(n)] ?? { time_start: '', time_end: '' }
                      return (
                        <tr key={n}>
                          <td className="fw-semibold">{n}</td>
                          <td>
                            <input
                              className="form-control form-control-sm"
                              placeholder="HH:MM"
                              value={c.time_start}
                              onChange={(e) => updateBell('common', n, 'time_start', e.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              className="form-control form-control-sm"
                              placeholder="HH:MM"
                              value={c.time_end}
                              onChange={(e) => updateBell('common', n, 'time_end', e.target.value)}
                            />
                          </td>
                          {hasClassDay && (
                            <>
                              <td>
                                <input
                                  className="form-control form-control-sm"
                                  placeholder="HH:MM"
                                  value={k.time_start}
                                  onChange={(e) => updateBell('class_day', n, 'time_start', e.target.value)}
                                />
                              </td>
                              <td>
                                <input
                                  className="form-control form-control-sm"
                                  placeholder="HH:MM"
                                  value={k.time_end}
                                  onChange={(e) => updateBell('class_day', n, 'time_end', e.target.value)}
                                />
                              </td>
                            </>
                          )}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <div className="modal-footer">
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
  )
}
