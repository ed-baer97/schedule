import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { apiJson } from '../api/client'
import { ModalPortal } from '../components/ModalPortal'

type Classroom = {
  id: number
  number: string
  name: string | null
  floor: number | null
  building: string | null
  classes_capacity: number | null
  display_name: string
}

export function ClassroomsPage() {
  const qc = useQueryClient()
  const [msg, setMsg] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [form, setForm] = useState({
    number: '',
    name: '',
    floor: '',
    building: '',
    classes_capacity: '1',
  })

  const q = useQuery({
    queryKey: ['classrooms'],
    queryFn: () => apiJson<Classroom[]>('/api/classrooms/'),
  })

  const saveM = useMutation({
    mutationFn: async () => {
      const payload = {
        number: form.number.trim(),
        name: form.name.trim() || null,
        floor: form.floor === '' ? null : Number(form.floor),
        building: form.building.trim() || null,
        classes_capacity: Number(form.classes_capacity || 1) || 1,
      }
      if (!payload.number) throw new Error('Укажите номер кабинета')
      if (editingId === 'new') {
        await apiJson('/api/classrooms/', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
      } else if (typeof editingId === 'number') {
        await apiJson(`/api/classrooms/${editingId}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      }
    },
    onSuccess: async () => {
      setMsg('Сохранено')
      setEditingId(null)
      await qc.invalidateQueries({ queryKey: ['classrooms'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  const delM = useMutation({
    mutationFn: (id: number) => apiJson<void>(`/api/classrooms/${id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      setMsg('Удалено')
      await qc.invalidateQueries({ queryKey: ['classrooms'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  useEffect(() => {
    if (!msg) return
    const t = setTimeout(() => setMsg(null), 4000)
    return () => clearTimeout(t)
  }, [msg])

  function openNew() {
    setForm({ number: '', name: '', floor: '', building: '', classes_capacity: '1' })
    setEditingId('new')
  }

  function openEdit(c: Classroom) {
    setForm({
      number: c.number,
      name: c.name ?? '',
      floor: c.floor === null || c.floor === undefined ? '' : String(c.floor),
      building: c.building ?? '',
      classes_capacity: String(c.classes_capacity ?? 1),
    })
    setEditingId(c.id)
  }

  if (q.isLoading) return <p>Загрузка…</p>
  if (q.isError) return <p className="text-danger">{(q.error as Error).message}</p>
  const rows = q.data ?? []

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h1 className="h3 mb-0">Кабинеты</h1>
        <button type="button" className="btn btn-primary" onClick={openNew}>
          Добавить
        </button>
      </div>
      {msg && <div className="alert alert-info py-2">{msg}</div>}
      <div className="table-responsive card shadow-sm">
        <table className="table table-hover mb-0">
          <thead className="table-light">
            <tr>
              <th>Номер</th>
              <th>Название</th>
              <th>Этаж</th>
              <th>Корпус</th>
              <th>Классов в слот</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id}>
                <td>{c.number}</td>
                <td>{c.name ?? '—'}</td>
                <td>{c.floor ?? '—'}</td>
                <td>{c.building ?? '—'}</td>
                <td>{c.classes_capacity ?? 1}</td>
                <td className="text-end text-nowrap">
                  <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => openEdit(c)}>
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

      {editingId !== null && (
        <ModalPortal>
        <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,.35)' }}>
          <div className="modal-dialog">
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
