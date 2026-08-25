import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  createClassroom,
  deleteClassroom,
  listClassrooms,
  updateClassroom,
  type Classroom,
} from '../api/classrooms'
import { listSubjects, type Subject } from '../api/subjects'
import { listTeachers, type Teacher } from '../api/teachers'
import { ModalPortal } from '../components/ModalPortal'
import { PageHeader } from '../components/PageHeader'

type FloorGroup = {
  key: string
  floor: number | null
  items: Classroom[]
}

function compareRoomNumber(a: Classroom, b: Classroom) {
  return a.number.localeCompare(b.number, 'ru', { numeric: true })
}

function groupByFloor(rows: Classroom[]): FloorGroup[] {
  const buckets = new Map<number | 'none', Classroom[]>()
  for (const room of rows) {
    const key = room.floor === null || room.floor === undefined ? 'none' : room.floor
    const list = buckets.get(key)
    if (list) list.push(room)
    else buckets.set(key, [room])
  }
  const floors = [...buckets.keys()].filter((k): k is number => k !== 'none').sort((a, b) => a - b)
  const groups: FloorGroup[] = floors.map((floor) => ({
    key: String(floor),
    floor,
    items: (buckets.get(floor) ?? []).slice().sort(compareRoomNumber),
  }))
  const unassigned = buckets.get('none')
  if (unassigned?.length) {
    groups.push({
      key: 'none',
      floor: null,
      items: unassigned.slice().sort(compareRoomNumber),
    })
  }
  return groups
}

function floorTitle(floor: number | null) {
  if (floor === null) return 'Этаж не указан'
  return `${floor} этаж`
}

function roomsWord(n: number) {
  const n10 = n % 10
  const n100 = n % 100
  if (n10 === 1 && n100 !== 11) return 'кабинет'
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return 'кабинета'
  return 'кабинетов'
}

export function ClassroomsPage() {
  const qc = useQueryClient()
  const [msg, setMsg] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [openKey, setOpenKey] = useState<string | null>(null)
  const openedOnce = useRef(false)
  const [form, setForm] = useState({
    number: '',
    name: '',
    floor: '',
    building: '',
    classes_capacity: '1',
    subject_id: '',
    is_exclusive: false,
    teacher_ids: [] as number[],
  })

  const q = useQuery({
    queryKey: ['classrooms'],
    queryFn: listClassrooms,
  })
  const subjectsQ = useQuery({
    queryKey: ['subjects', 'all'],
    queryFn: () => listSubjects('all'),
  })
  const teachersQ = useQuery({
    queryKey: ['teachers'],
    queryFn: listTeachers,
  })

  const saveM = useMutation({
    mutationFn: async () => {
      const payload = {
        number: form.number.trim(),
        name: form.name.trim() || null,
        floor: form.floor === '' ? null : Number(form.floor),
        building: form.building.trim() || null,
        classes_capacity: Number(form.classes_capacity || 1) || 1,
        subject_id: form.subject_id === '' ? null : Number(form.subject_id),
        is_exclusive: form.subject_id === '' ? false : form.is_exclusive,
        teacher_ids: form.teacher_ids,
      }
      if (!payload.number) throw new Error('Укажите номер кабинета')
      if (payload.is_exclusive && payload.subject_id === null) {
        throw new Error('Фиксированный кабинет должен иметь предмет')
      }
      if (editingId === 'new') {
        await createClassroom(payload)
      } else if (typeof editingId === 'number') {
        await updateClassroom(editingId, payload)
      }
    },
    onSuccess: async () => {
      setMsg('Сохранено')
      setEditingId(null)
      await qc.invalidateQueries({ queryKey: ['classrooms'] })
      await qc.invalidateQueries({ queryKey: ['subjects'] })
      await qc.invalidateQueries({ queryKey: ['teachers'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  const delM = useMutation({
    mutationFn: deleteClassroom,
    onSuccess: async () => {
      setMsg('Удалено')
      await qc.invalidateQueries({ queryKey: ['classrooms'] })
      await qc.invalidateQueries({ queryKey: ['subjects'] })
      await qc.invalidateQueries({ queryKey: ['teachers'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  useEffect(() => {
    if (!msg) return
    const t = setTimeout(() => setMsg(null), 4000)
    return () => clearTimeout(t)
  }, [msg])

  const rows = q.data ?? []
  const subjects = subjectsQ.data ?? []
  const teachers = teachersQ.data ?? []
  const subjectById = useMemo(() => {
    const m = new Map<number, Subject>()
    for (const s of subjects) m.set(s.id, s)
    return m
  }, [subjects])
  const groups = useMemo(() => groupByFloor(rows), [rows])

  useEffect(() => {
    if (openedOnce.current || groups.length === 0) return
    openedOnce.current = true
    setOpenKey(groups[0].key)
  }, [groups])

  function openNew() {
    setForm({
      number: '',
      name: '',
      floor: '',
      building: '',
      classes_capacity: '1',
      subject_id: '',
      is_exclusive: false,
      teacher_ids: [],
    })
    setEditingId('new')
  }

  function openEdit(c: Classroom) {
    setForm({
      number: c.number,
      name: c.name ?? '',
      floor: c.floor === null || c.floor === undefined ? '' : String(c.floor),
      building: c.building ?? '',
      classes_capacity: String(c.classes_capacity ?? 1),
      subject_id: c.subject_id === null || c.subject_id === undefined ? '' : String(c.subject_id),
      is_exclusive: Boolean(c.is_exclusive),
      teacher_ids: (c.teachers ?? []).map((t) => t.id),
    })
    setEditingId(c.id)
  }

  function toggleTeacher(id: number) {
    setForm((f) => ({
      ...f,
      teacher_ids: f.teacher_ids.includes(id)
        ? f.teacher_ids.filter((tid) => tid !== id)
        : [...f.teacher_ids, id],
    }))
  }

  function otherRoomHint(t: Teacher) {
    if (!t.home_classroom_id) return null
    if (typeof editingId === 'number' && t.home_classroom_id === editingId) return null
    return t.home_classroom?.display_name ?? null
  }

  function onSubjectChange(value: string) {
    const subj = value === '' ? null : subjectById.get(Number(value))
    setForm((f) => ({
      ...f,
      subject_id: value,
      is_exclusive: value === '' ? false : subj?.requires_fixed_classroom ? true : f.is_exclusive,
    }))
  }

  if (q.isLoading) return <p>Загрузка…</p>
  if (q.isError) return <p className="text-danger">{(q.error as Error).message}</p>

  return (
    <div>
      <PageHeader
        title="Кабинеты"
        subtitle="Сгруппированы по этажам. За кабинетом можно закрепить нескольких учителей"
        actions={
          <button type="button" className="btn btn-primary" onClick={openNew}>
            <i className="bi bi-plus-lg me-1" />
            Добавить
          </button>
        }
      />
      {msg && (
        <div className="alert alert-info py-2" role="status">
          {msg}
        </div>
      )}

      {groups.length === 0 ? (
        <div className="card shadow-sm">
          <div className="card-body text-muted">Кабинетов пока нет — добавьте первый.</div>
        </div>
      ) : (
        <div className="accordion classrooms-accordion" id="classrooms-by-floor">
          {groups.map((group) => {
            const open = openKey === group.key
            return (
              <div className="accordion-item" key={group.key}>
                <h2 className="accordion-header">
                  <button
                    className={`accordion-button ${open ? '' : 'collapsed'}`}
                    type="button"
                    aria-expanded={open}
                    onClick={() => setOpenKey(open ? null : group.key)}
                  >
                    <span className="me-2">{floorTitle(group.floor)}</span>
                    <span className="badge rounded-pill classrooms-floor-count">
                      {group.items.length} {roomsWord(group.items.length)}
                    </span>
                  </button>
                </h2>
                <div className={`accordion-collapse collapse ${open ? 'show' : ''}`}>
                  <div className="accordion-body p-0">
                    <div className="table-responsive">
                      <table className="table table-hover mb-0">
                        <thead className="table-light">
                          <tr>
                            <th>Номер</th>
                            <th>Название</th>
                            <th>Предмет</th>
                            <th>Учителя</th>
                            <th>Корпус</th>
                            <th>Классов в слот</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {group.items.map((c) => (
                            <tr key={c.id}>
                              <td>{c.number}</td>
                              <td>{c.name ?? '—'}</td>
                              <td>
                                {c.subject?.name ?? '—'}
                                {c.is_exclusive && c.subject ? (
                                  <span className="badge text-bg-secondary ms-1">фикс.</span>
                                ) : null}
                              </td>
                              <td>
                                {(c.teachers ?? []).length === 0
                                  ? '—'
                                  : (c.teachers ?? []).map((t) => t.full_name).join(', ')}
                              </td>
                              <td>{c.building ?? '—'}</td>
                              <td>{c.classes_capacity ?? 1}</td>
                              <td className="text-end text-nowrap">
                                <button
                                  type="button"
                                  className="btn btn-sm btn-outline-secondary me-1"
                                  onClick={() => openEdit(c)}
                                >
                                  Изменить
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-sm btn-outline-danger"
                                  onClick={() => {
                                    if (confirm(`Удалить кабинет «${c.display_name}»?`)) delM.mutate(c.id)
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
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {editingId !== null && (
        <ModalPortal>
        <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,.35)' }}>
          <div className="modal-dialog modal-dialog-scrollable">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">{editingId === 'new' ? 'Новый кабинет' : 'Редактирование'}</h5>
                <button type="button" className="btn-close" onClick={() => setEditingId(null)} aria-label="Закрыть" />
              </div>
              <div className="modal-body">
                <div className="mb-2">
                  <label className="form-label">Номер</label>
                  <input className="form-control" value={form.number} onChange={(e) => setForm((f) => ({ ...f, number: e.target.value }))} />
                </div>
                <div className="mb-2">
                  <label className="form-label">Название</label>
                  <input className="form-control" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
                </div>
                <div className="mb-2">
                  <label className="form-label">Предмет</label>
                  <select
                    className="form-select"
                    value={form.subject_id}
                    onChange={(e) => onSubjectChange(e.target.value)}
                  >
                    <option value="">— общий —</option>
                    {subjects.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                        {s.requires_fixed_classroom ? ' (фикс.)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-check mb-2">
                  <input
                    className="form-check-input"
                    type="checkbox"
                    id="roomExclusive"
                    checked={form.is_exclusive}
                    disabled={form.subject_id === ''}
                    onChange={(e) => setForm((f) => ({ ...f, is_exclusive: e.target.checked }))}
                  />
                  <label className="form-check-label" htmlFor="roomExclusive">
                    Фиксированный — только этот предмет
                  </label>
                </div>
                <div className="mb-2">
                  <label className="form-label">Учителя</label>
                  {teachers.length === 0 ? (
                    <div className="form-text">Сначала добавьте учителей в справочник.</div>
                  ) : (
                    <div className="classroom-teachers-picker border rounded px-2 py-1">
                      {teachers.map((t) => {
                        const hint = otherRoomHint(t)
                        const checked = form.teacher_ids.includes(t.id)
                        return (
                          <div className="form-check" key={t.id}>
                            <input
                              className="form-check-input"
                              type="checkbox"
                              id={`room-teacher-${t.id}`}
                              checked={checked}
                              onChange={() => toggleTeacher(t.id)}
                            />
                            <label className="form-check-label" htmlFor={`room-teacher-${t.id}`}>
                              {t.full_name}
                              {hint ? (
                                <span className="text-muted"> · сейчас {hint}</span>
                              ) : null}
                            </label>
                          </div>
                        )
                      })}
                    </div>
                  )}
                  <div className="form-text">
                    Можно закрепить нескольких учителей. Если учитель уже в другом кабинете, он будет
                    перенесён сюда.
                  </div>
                </div>
                <div className="mb-2">
                  <label className="form-label">Этаж</label>
                  <input className="form-control" type="number" value={form.floor} onChange={(e) => setForm((f) => ({ ...f, floor: e.target.value }))} />
                </div>
                <div className="mb-2">
                  <label className="form-label">Корпус</label>
                  <input className="form-control" value={form.building} onChange={(e) => setForm((f) => ({ ...f, building: e.target.value }))} />
                </div>
                <div className="mb-2">
                  <label className="form-label">Классов в слот</label>
                  <input
                    className="form-control"
                    type="number"
                    min={1}
                    value={form.classes_capacity}
                    onChange={(e) => setForm((f) => ({ ...f, classes_capacity: e.target.value }))}
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setEditingId(null)}>
                  Отмена
                </button>
                <button type="button" className="btn btn-primary" disabled={saveM.isPending} onClick={() => saveM.mutate()}>
                  Сохранить
                </button>
              </div>
            </div>
          </div>
        </div>
        </ModalPortal>
      )}
    </div>
  )
}
