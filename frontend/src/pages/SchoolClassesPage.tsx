import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import {
  batchAssignShift,
  createSchoolClass,
  deleteSchoolClass,
  listSchoolClasses,
  updateSchoolClass,
  type SchoolClass,
} from '../api/schoolClasses'
import { listClassrooms } from '../api/classrooms'
import { listShifts } from '../api/shifts'
import { ModalPortal } from '../components/ModalPortal'

export function SchoolClassesPage() {
  const qc = useQueryClient()
  const [msg, setMsg] = useState<string | null>(null)
  const [selected, setSelected] = useState<Record<number, boolean>>({})
  const [batchShiftId, setBatchShiftId] = useState<string>('')
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [form, setForm] = useState({
    name: '',
    school_level: 'elementary',
    shift_id: '',
    home_classroom_id: '',
  })

  const classesQ = useQuery({
    queryKey: ['school-classes'],
    queryFn: listSchoolClasses,
  })
  const shiftsQ = useQuery({
    queryKey: ['shifts'],
    queryFn: listShifts,
  })
  const roomsQ = useQuery({
    queryKey: ['classrooms'],
    queryFn: listClassrooms,
  })

  const saveM = useMutation({
    mutationFn: async () => {
      const payload = {
        name: form.name.trim(),
        school_level: form.school_level,
        shift_id: form.shift_id === '' ? null : Number(form.shift_id),
        home_classroom_id: form.home_classroom_id === '' ? null : Number(form.home_classroom_id),
      }
      if (!payload.name) throw new Error('Укажите название класса')
      if (editingId === 'new') {
        await createSchoolClass(payload)
      } else if (typeof editingId === 'number') {
        await updateSchoolClass(editingId, payload)
      }
    },
    onSuccess: async () => {
      setMsg('Сохранено')
      setEditingId(null)
      await qc.invalidateQueries({ queryKey: ['school-classes'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  const delM = useMutation({
    mutationFn: deleteSchoolClass,
    onSuccess: async () => {
      setMsg('Удалено')
      await qc.invalidateQueries({ queryKey: ['school-classes'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  const batchM = useMutation({
    mutationFn: async () => {
      const ids = Object.entries(selected)
        .filter(([, v]) => v)
        .map(([k]) => Number(k))
      if (!ids.length) throw new Error('Отметьте классы')
      await batchAssignShift(ids, batchShiftId === '' ? null : Number(batchShiftId))
    },
    onSuccess: async () => {
      setMsg('Смена обновлена')
      setSelected({})
      await qc.invalidateQueries({ queryKey: ['school-classes'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  useEffect(() => {
    if (!msg) return
    const t = setTimeout(() => setMsg(null), 4000)
    return () => clearTimeout(t)
  }, [msg])

  function openNew() {
    setForm({ name: '', school_level: 'elementary', shift_id: '', home_classroom_id: '' })
    setEditingId('new')
  }

  function openEdit(c: SchoolClass) {
    setForm({
      name: c.name,
      school_level: c.school_level,
      shift_id: c.shift_id === null ? '' : String(c.shift_id),
      home_classroom_id: c.home_classroom_id === null ? '' : String(c.home_classroom_id),
    })
    setEditingId(c.id)
  }

  function toggle(id: number) {
    setSelected((s) => ({ ...s, [id]: !s[id] }))
  }

  if (classesQ.isLoading || shiftsQ.isLoading || roomsQ.isLoading) return <p>Загрузка…</p>
  if (classesQ.isError) return <p className="text-danger">{(classesQ.error as Error).message}</p>

  const classes = classesQ.data ?? []
  const shifts = shiftsQ.data ?? []
  const rooms = roomsQ.data ?? []

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h1 className="h3 mb-0">Классы</h1>
        <button type="button" className="btn btn-primary" onClick={openNew}>
          Добавить
        </button>
      </div>
      {msg && <div className="alert alert-info py-2">{msg}</div>}

      <div className="card shadow-sm mb-3">
        <div className="card-body row g-2 align-items-end">
          <div className="col-md-4">
            <label className="form-label small mb-0">Смена для выбранных</label>
            <select className="form-select" value={batchShiftId} onChange={(e) => setBatchShiftId(e.target.value)}>
              <option value="">— сбросить —</option>
              {shifts.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.school_level === 'elementary' ? 'НШ' : 'ОШ'})
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-4">
            <button type="button" className="btn btn-outline-primary" disabled={batchM.isPending} onClick={() => batchM.mutate()}>
              Применить смену
            </button>
          </div>
        </div>
      </div>

      <div className="table-responsive card shadow-sm">
        <table className="table table-hover mb-0">
          <thead className="table-light">
            <tr>
              <th style={{ width: 40 }} />
              <th>Класс</th>
              <th>Уровень</th>
              <th>Смена</th>
              <th>Классная</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {classes.map((c) => (
              <tr key={c.id}>
                <td>
                  <input type="checkbox" checked={!!selected[c.id]} onChange={() => toggle(c.id)} />
                </td>
                <td>{c.name}</td>
                <td>{c.school_level_display}</td>
                <td>{c.shift?.name ?? '—'}</td>
                <td>{c.home_classroom?.display_name ?? '—'}</td>
                <td className="text-end text-nowrap">
                  <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => openEdit(c)}>
                    Изменить
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-danger"
                    onClick={() => {
                      if (confirm(`Удалить класс «${c.name}»?`)) delM.mutate(c.id)
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
        <ModalPortal>
        <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,.35)' }}>
          <div className="modal-dialog">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">{editingId === 'new' ? 'Новый класс' : 'Редактирование'}</h5>
                <button type="button" className="btn-close" onClick={() => setEditingId(null)} aria-label="Закрыть" />
              </div>
              <div className="modal-body">
                <div className="mb-2">
                  <label className="form-label">Название (например 5А)</label>
                  <input className="form-control" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
                </div>
                <div className="mb-2">
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
                <div className="mb-2">
                  <label className="form-label">Смена</label>
                  <select
                    className="form-select"
                    value={form.shift_id}
                    onChange={(e) => setForm((f) => ({ ...f, shift_id: e.target.value }))}
                  >
                    <option value="">—</option>
                    {shifts.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="mb-2">
                  <label className="form-label">Классная</label>
                  <select
                    className="form-select"
                    value={form.home_classroom_id}
                    onChange={(e) => setForm((f) => ({ ...f, home_classroom_id: e.target.value }))}
                  >
                    <option value="">—</option>
                    {rooms.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.display_name}
                      </option>
                    ))}
                  </select>
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
