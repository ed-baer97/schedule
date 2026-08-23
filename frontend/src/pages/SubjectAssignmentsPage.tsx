import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { apiJson } from '../api/client'

type ClassRow = {
  id: number
  name: string
  grade: number
  hours_per_week: number
  teacher_ids: number[]
  is_split: boolean
}

type TeacherRow = { id: number; full_name: string }

type AssignmentsView = {
  subject: {
    id: number
    name: string
    display_color: string
  }
  school_level: string
  classes: ClassRow[]
  attached_teachers: TeacherRow[]
  all_teachers: TeacherRow[]
}

type LocalState = {
  teacherIds: number[]
  selections: Record<number, Set<number>>
}

function buildLocal(view: AssignmentsView): LocalState {
  const selections: Record<number, Set<number>> = {}
  for (const t of view.attached_teachers) {
    selections[t.id] = new Set()
  }
  for (const c of view.classes) {
    for (const tid of c.teacher_ids) {
      selections[tid] ??= new Set()
      selections[tid].add(c.id)
    }
  }
  return {
    teacherIds: view.attached_teachers.map((t) => t.id),
    selections,
  }
}

export function SubjectAssignmentsPage() {
  const { id } = useParams<{ id: string }>()
  const subjectId = Number(id)
  const [params, setParams] = useSearchParams()
  const schoolLevel = (params.get('school_level') as 'elementary' | 'secondary') || 'elementary'
  const qc = useQueryClient()
  const [msg, setMsg] = useState<string | null>(null)
  const [local, setLocal] = useState<LocalState | null>(null)
  const [pendingTeacher, setPendingTeacher] = useState<string>('')

  const q = useQuery({
    queryKey: ['subject-assignments', subjectId, schoolLevel],
    queryFn: () =>
      apiJson<AssignmentsView>(
        `/api/subjects/${subjectId}/assignments?school_level=${schoolLevel}`,
      ),
    enabled: Number.isFinite(subjectId),
  })

  useEffect(() => {
    if (q.data) setLocal(buildLocal(q.data))
  }, [q.data])

  useEffect(() => {
    if (!msg) return
    const t = setTimeout(() => setMsg(null), 5000)
    return () => clearTimeout(t)
  }, [msg])

  const saveM = useMutation({
    mutationFn: async () => {
      if (!local || !q.data) throw new Error('Нет данных')
      const selections: Record<string, number[]> = {}
      for (const c of q.data.classes) {
        const arr: number[] = []
        for (const tid of local.teacherIds) {
          if (local.selections[tid]?.has(c.id)) arr.push(tid)
        }
        selections[String(c.id)] = arr
      }
      const body = {
        school_level: schoolLevel,
        teacher_ids: local.teacherIds,
        selections,
      }
      const res = await apiJson<{ ok: boolean; errors: string[] }>(
        `/api/subjects/${subjectId}/assignments`,
        { method: 'POST', body: JSON.stringify(body) },
      )
      if (!res.ok) throw new Error(res.errors.join('; ') || 'Ошибка сохранения')
      return res
    },
    onSuccess: async () => {
      setMsg('Назначения сохранены')
      await qc.invalidateQueries({ queryKey: ['subject-assignments', subjectId, schoolLevel] })
      await qc.invalidateQueries({ queryKey: ['assignments'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  const view = q.data
  const availableForAdd = useMemo(() => {
    if (!view || !local) return []
    const used = new Set(local.teacherIds)
    return view.all_teachers.filter((t) => !used.has(t.id))
  }, [view, local])

  if (q.isLoading) return <p>Загрузка…</p>
  if (q.isError) return <p className="text-danger">{(q.error as Error).message}</p>
  if (!view || !local) return null

  const notAssigned = view.classes.filter(
    (c) => !local.teacherIds.some((tid) => local.selections[tid]?.has(c.id)),
  )
  const split = view.classes.filter((c) => {
    const count = local.teacherIds.filter((tid) => local.selections[tid]?.has(c.id)).length
    return count >= 2
  })

  function addTeacher() {
    const tid = Number(pendingTeacher)
    if (!tid) return
    setLocal((prev) => {
      if (!prev) return prev
      if (prev.teacherIds.includes(tid)) return prev
      return {
        teacherIds: [...prev.teacherIds, tid],
        selections: { ...prev.selections, [tid]: new Set() },
      }
    })
    setPendingTeacher('')
  }

  function removeTeacher(tid: number) {
    setLocal((prev) => {
      if (!prev) return prev
      const { [tid]: _drop, ...rest } = prev.selections
      void _drop
      return {
        teacherIds: prev.teacherIds.filter((x) => x !== tid),
        selections: rest,
      }
    })
  }

  function toggleClass(tid: number, classId: number, checked: boolean) {
    setLocal((prev) => {
      if (!prev) return prev
      const set = new Set(prev.selections[tid] ?? [])
      if (checked) set.add(classId)
      else set.delete(classId)
      return { ...prev, selections: { ...prev.selections, [tid]: set } }
    })
  }

  return (
    <div>
      <div className="d-flex align-items-center gap-2 mb-3 flex-wrap">
        <Link to={`/subjects`} className="text-muted text-decoration-none">
          ← Предметы
        </Link>
      </div>
      <h1 className="h3 mb-3 d-flex align-items-center gap-2">
        <span
          className="d-inline-block rounded"
          style={{ width: 22, height: 22, background: 'white', border: `2px solid ${view.subject.display_color}` }}
        />
        {view.subject.name}
        <small className="text-muted fs-6">— Назначения учителей</small>
      </h1>

      <ul className="nav nav-tabs mb-3">
        <li className="nav-item">
          <button
            type="button"
            className={`nav-link ${schoolLevel === 'elementary' ? 'active' : ''}`}
            onClick={() => setParams({ school_level: 'elementary' })}
          >
            Начальная школа
          </button>
        </li>
        <li className="nav-item">
          <button
            type="button"
            className={`nav-link ${schoolLevel === 'secondary' ? 'active' : ''}`}
            onClick={() => setParams({ school_level: 'secondary' })}
          >
            Основная школа
          </button>
        </li>
      </ul>

      {msg && <div className="alert alert-info py-2">{msg}</div>}

      {view.classes.length === 0 ? (
        <div className="card">
          <div className="card-body text-center py-5 text-muted">
            <p className="mb-1">
              Для этого предмета нет записей нагрузки в
              {schoolLevel === 'elementary' ? ' начальной' : ' основной'} школе.
            </p>
            <p className="mb-0">
              Сначала добавьте часы на странице{' '}
              <Link to="/workload">Нагрузка</Link> или{' '}
              <Link to="/import">импортируйте файлы нагрузки по предметам</Link>.
            </p>
          </div>
        </div>
      ) : (
        <>
          <div className="row mb-3 g-3">
            <div className="col-md-6">
              <div className="alert alert-warning mb-0">
                <div className="fw-semibold mb-1">Не назначены учителя</div>
                {notAssigned.length === 0 ? (
                  <span className="text-muted">Все классы имеют назначенных учителей</span>
                ) : (
                  notAssigned.map((c) => (
                    <span key={c.id} className="badge bg-warning text-dark me-1 mb-1">
                      {c.name}
                    </span>
                  ))
                )}
              </div>
            </div>
            <div className="col-md-6">
              <div className="alert alert-info mb-0">
                <div className="fw-semibold mb-1">Поделены на подгруппы</div>
                {split.length === 0 ? (
                  <span className="text-muted">Подразделений нет</span>
                ) : (
                  split.map((c) => (
                    <span key={c.id} className="badge bg-info text-dark me-1 mb-1">
                      {c.name}
                    </span>
                  ))
                )}
              </div>
            </div>
          </div>

          <div className="d-flex gap-2 align-items-center mb-3 flex-wrap">
            <select
              className="form-select"
              style={{ maxWidth: 350 }}
              value={pendingTeacher}
              onChange={(e) => setPendingTeacher(e.target.value)}
            >
              <option value="">Выберите учителя…</option>
              {availableForAdd.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.full_name}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-outline-primary"
              disabled={!pendingTeacher}
              onClick={addTeacher}
            >
              Добавить
            </button>
          </div>

          {local.teacherIds.length === 0 ? (
            <div className="text-center py-4 text-muted">
              Добавьте учителей, преподающих этот предмет.
            </div>
          ) : (
            local.teacherIds.map((tid) => {
              const teacher = view.all_teachers.find((t) => t.id === tid)
              if (!teacher) return null
              const selected = local.selections[tid] ?? new Set<number>()
              return (
                <div key={tid} className="card shadow-sm mb-3">
                  <div className="card-body">
                    <div className="d-flex justify-content-between align-items-center mb-2 pb-2 border-bottom">
                      <span className="fw-semibold">{teacher.full_name}</span>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-danger"
                        onClick={() => removeTeacher(tid)}
                        title="Убрать учителя"
                      >
                        Убрать
                      </button>
                    </div>
                    <div className="d-flex flex-wrap gap-2">
                      {view.classes.map((c) => {
                        const checked = selected.has(c.id)
                        return (
                          <label
                            key={c.id}
                            className={`d-inline-flex align-items-center gap-2 px-3 py-1 border rounded ${
                              checked ? 'bg-info-subtle border-info' : ''
                            }`}
                            style={{ cursor: 'pointer' }}
                          >
                            <input
                              type="checkbox"
                              className="form-check-input m-0"
                              checked={checked}
                              onChange={(e) => toggleClass(tid, c.id, e.target.checked)}
                            />
                            <span>{c.name}</span>
                            <span className="text-muted small">{c.hours_per_week}ч</span>
                          </label>
                        )
                      })}
                    </div>
                  </div>
                </div>
              )
            })
          )}

          <div className="d-flex justify-content-between align-items-center mt-3">
            <div className="text-muted small">
              Если 2 учителя отмечены для одного класса — он автоматически делится на подгруппы.
            </div>
            <button
              type="button"
              className="btn btn-primary btn-lg"
              disabled={saveM.isPending}
              onClick={() => saveM.mutate()}
            >
              {saveM.isPending ? 'Сохранение…' : 'Сохранить'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
