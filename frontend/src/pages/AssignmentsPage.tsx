import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { apiJson } from '../api/client'

type SchoolLevel = 'elementary' | 'secondary'

type SubjectBrief = { id: number; name: string; display_color: string }
type TeacherBrief = { id: number; full_name: string }
type ClassBrief = { id: number; name: string; school_level: string; grade: number }
type ClassroomBrief = { id: number; number: string; name: string | null; display_name: string }

type Assignment = {
  id: number
  subject_id: number
  teacher_id: number | null
  class_id: number
  hours_per_week: number
  group_number: number | null
  preferred_classroom_id: number | null
  subject: SubjectBrief
  teacher: TeacherBrief | null
  school_class: ClassBrief
  preferred_classroom: ClassroomBrief | null
}

type FormState = {
  id: number | null
  subject_id: number | ''
  teacher_id: number | ''
  class_id: number | ''
  hours_per_week: number
  group_number: number | ''
  preferred_classroom_id: number | ''
}

const emptyForm: FormState = {
  id: null,
  subject_id: '',
  teacher_id: '',
  class_id: '',
  hours_per_week: 1,
  group_number: '',
  preferred_classroom_id: '',
}

export function AssignmentsPage() {
  const qc = useQueryClient()
  const [level, setLevel] = useState<SchoolLevel>('elementary')
  const [msg, setMsg] = useState<{ kind: 'success' | 'danger'; text: string } | null>(null)
  const [form, setForm] = useState<FormState | null>(null)

  useEffect(() => {
    if (!msg) return
    const t = setTimeout(() => setMsg(null), 4000)
    return () => clearTimeout(t)
  }, [msg])

  const listQ = useQuery({
    queryKey: ['assignments', level],
    queryFn: () => apiJson<Assignment[]>(`/api/assignments/?school_level=${level}`),
  })
  const teachersQ = useQuery({
    queryKey: ['teachers'],
    queryFn: () => apiJson<TeacherBrief[]>('/api/teachers/'),
  })
  const subjectsQ = useQuery({
    queryKey: ['subjects'],
    queryFn: () => apiJson<SubjectBrief[]>('/api/subjects/'),
  })
  const classesQ = useQuery({
    queryKey: ['school-classes'],
    queryFn: () => apiJson<ClassBrief[]>('/api/school-classes/'),
  })
  const classroomsQ = useQuery({
    queryKey: ['classrooms'],
    queryFn: () => apiJson<ClassroomBrief[]>('/api/classrooms/'),
  })

  const saveM = useMutation({
    mutationFn: async (f: FormState) => {
      if (f.subject_id === '' || f.class_id === '') {
        throw new Error('Выберите класс и предмет')
      }
      const payload = {
        subject_id: Number(f.subject_id),
        class_id: Number(f.class_id),
        hours_per_week: Number(f.hours_per_week),
        teacher_id: f.teacher_id === '' ? null : Number(f.teacher_id),
        group_number: f.group_number === '' ? null : Number(f.group_number),
        preferred_classroom_id:
          f.preferred_classroom_id === '' ? null : Number(f.preferred_classroom_id),
      }
      if (f.id == null) {
        await apiJson<Assignment>('/api/assignments/', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
      } else {
        await apiJson<Assignment>(`/api/assignments/${f.id}`, {
          method: 'PUT',
          body: JSON.stringify({
            ...payload,
            clear_teacher: payload.teacher_id == null,
            clear_group: payload.group_number == null,
            clear_preferred_classroom: payload.preferred_classroom_id == null,
          }),
        })
      }
    },
    onSuccess: async () => {
      setForm(null)
      setMsg({ kind: 'success', text: 'Сохранено' })
      await qc.invalidateQueries({ queryKey: ['assignments'] })
    },
    onError: (e: Error) => setMsg({ kind: 'danger', text: e.message }),
  })

  const setTeacherM = useMutation({
    mutationFn: (p: { id: number; teacher_id: number | null }) =>
      apiJson<Assignment>(`/api/assignments/${p.id}/teacher`, {
        method: 'PATCH',
        body: JSON.stringify({ teacher_id: p.teacher_id }),
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['assignments'] })
    },
    onError: (e: Error) => setMsg({ kind: 'danger', text: e.message }),
  })

  const deleteM = useMutation({
    mutationFn: (id: number) =>
      apiJson<void>(`/api/assignments/${id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      setMsg({ kind: 'success', text: 'Удалено' })
      await qc.invalidateQueries({ queryKey: ['assignments'] })
    },
    onError: (e: Error) => setMsg({ kind: 'danger', text: e.message }),
  })

  if (
    listQ.isLoading ||
    teachersQ.isLoading ||
    subjectsQ.isLoading ||
    classesQ.isLoading ||
    classroomsQ.isLoading
  ) {
    return <p>Загрузка…</p>
  }
  if (listQ.isError) return <p className="text-danger">{(listQ.error as Error).message}</p>

  const assignments = listQ.data ?? []
  const teachers = teachersQ.data ?? []
  const subjects = subjectsQ.data ?? []
  const classes = (classesQ.data ?? []).filter((c) => c.school_level === level)
  const classrooms = classroomsQ.data ?? []
  const unassigned = assignments.filter((a) => a.teacher == null).length

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h1 className="h3 mb-0">Назначения</h1>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => setForm({ ...emptyForm })}
        >
          Добавить
        </button>
      </div>

      {msg && <div className={`alert alert-${msg.kind} py-2`}>{msg.text}</div>}

      <ul className="nav nav-tabs mb-3">
        <li className="nav-item">
          <button
            type="button"
            className={`nav-link ${level === 'elementary' ? 'active' : ''}`}
            onClick={() => setLevel('elementary')}
          >
            Начальная школа
          </button>
        </li>
        <li className="nav-item">
          <button
            type="button"
            className={`nav-link ${level === 'secondary' ? 'active' : ''}`}
            onClick={() => setLevel('secondary')}
          >
            Основная школа
          </button>
        </li>
      </ul>

      {unassigned > 0 && (
        <div className="alert alert-warning py-2">
          {unassigned} назначений без учителя.
        </div>
      )}

      <div className="card">
        <div className="table-responsive">
          <table className="table table-hover mb-0">
            <thead className="table-light">
              <tr>
                <th>Класс</th>
                <th>Предмет</th>
                <th>Часов/нед</th>
                <th>Группа</th>
                <th>Учитель</th>
                <th>Каб.</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {assignments.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center text-muted py-4">
                    Назначения не найдены. Добавьте нагрузку или импортируйте Excel.
                  </td>
                </tr>
              ) : (
                assignments.map((a) => (
                  <tr key={a.id} className={a.teacher == null ? 'table-warning' : ''}>
                    <td className="fw-semibold">{a.school_class.name}</td>
                    <td>
                      <span
                        className="d-inline-block me-1"
                        style={{
                          width: 10,
                          height: 10,
                          borderRadius: '50%',
                          background: a.subject.display_color,
                          border: '1px solid #ccc',
                        }}
                      />
                      {a.subject.name}
                    </td>
                    <td>{a.hours_per_week}</td>
                    <td>
                      {a.group_number ? (
                        <span className="badge bg-info">Группа {a.group_number}</span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      <select
                        className="form-select form-select-sm"
                        style={{ minWidth: 180 }}
                        value={a.teacher_id == null ? '' : String(a.teacher_id)}
                        onChange={(e) =>
                          setTeacherM.mutate({
                            id: a.id,
                            teacher_id: e.target.value === '' ? null : Number(e.target.value),
                          })
                        }
                      >
                        <option value="">— Не назначен —</option>
                        {teachers.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.full_name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>{a.preferred_classroom?.display_name ?? '—'}</td>
                    <td className="text-end text-nowrap">
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-secondary me-1"
                        onClick={() =>
                          setForm({
                            id: a.id,
                            subject_id: a.subject_id,
                            teacher_id: a.teacher_id ?? '',
                            class_id: a.class_id,
                            hours_per_week: a.hours_per_week,
                            group_number: a.group_number ?? '',
                            preferred_classroom_id: a.preferred_classroom_id ?? '',
                          })
                        }
                      >
                        Изменить
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-danger"
                        onClick={() => {
                          if (confirm('Удалить назначение?')) deleteM.mutate(a.id)
                        }}
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {form && (
        <div
          className="modal show d-block"
          tabIndex={-1}
          style={{ background: 'rgba(0,0,0,.35)' }}
        >
          <div className="modal-dialog modal-lg">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">
                  {form.id == null ? 'Новое назначение' : 'Редактирование'}
                </h5>
                <button
                  type="button"
                  className="btn-close"
                  aria-label="Закрыть"
                  onClick={() => setForm(null)}
                />
              </div>
              <div className="modal-body">
                <div className="row g-3">
                  <div className="col-md-4">
                    <label className="form-label">Класс</label>
                    <select
                      className="form-select"
                      value={form.class_id === '' ? '' : String(form.class_id)}
                      onChange={(e) =>
                        setForm((f) =>
                          f
                            ? {
                                ...f,
                                class_id:
                                  e.target.value === '' ? '' : Number(e.target.value),
                              }
                            : f,
                        )
                      }
                    >
                      <option value="">—</option>
                      {classes.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">Предмет</label>
                    <select
                      className="form-select"
                      value={form.subject_id === '' ? '' : String(form.subject_id)}
                      onChange={(e) =>
                        setForm((f) =>
                          f
                            ? {
                                ...f,
                                subject_id:
                                  e.target.value === '' ? '' : Number(e.target.value),
                              }
                            : f,
                        )
                      }
                    >
                      <option value="">—</option>
                      {subjects.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">Часов/нед</label>
                    <input
                      type="number"
                      className="form-control"
                      min={1}
                      max={30}
                      value={form.hours_per_week}
                      onChange={(e) =>
                        setForm((f) =>
                          f ? { ...f, hours_per_week: Number(e.target.value) || 1 } : f,
                        )
                      }
                    />
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">Учитель</label>
                    <select
                      className="form-select"
                      value={form.teacher_id === '' ? '' : String(form.teacher_id)}
                      onChange={(e) =>
                        setForm((f) =>
                          f
                            ? {
                                ...f,
                                teacher_id:
                                  e.target.value === '' ? '' : Number(e.target.value),
                              }
                            : f,
                        )
                      }
                    >
                      <option value="">— Не назначен —</option>
                      {teachers.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.full_name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">Группа</label>
                    <select
                      className="form-select"
                      value={form.group_number === '' ? '' : String(form.group_number)}
                      onChange={(e) =>
                        setForm((f) =>
                          f
                            ? {
                                ...f,
                                group_number:
                                  e.target.value === '' ? '' : Number(e.target.value),
                              }
                            : f,
                        )
                      }
                    >
                      <option value="">Весь класс</option>
                      <option value="1">Группа 1</option>
                      <option value="2">Группа 2</option>
                    </select>
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">Предпочтительный кабинет</label>
                    <select
                      className="form-select"
                      value={
                        form.preferred_classroom_id === ''
                          ? ''
                          : String(form.preferred_classroom_id)
                      }
                      onChange={(e) =>
                        setForm((f) =>
                          f
                            ? {
                                ...f,
                                preferred_classroom_id:
                                  e.target.value === '' ? '' : Number(e.target.value),
                              }
                            : f,
                        )
                      }
                    >
                      <option value="">— Любой —</option>
                      {classrooms.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.display_name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setForm(null)}
                >
                  Отмена
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={saveM.isPending}
                  onClick={() => saveM.mutate(form)}
                >
                  Сохранить
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
