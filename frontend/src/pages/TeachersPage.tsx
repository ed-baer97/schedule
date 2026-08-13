import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { apiJson } from '../api/client'

type Classroom = {
  id: number
  display_name: string
}

type Teacher = {
  id: number
  full_name: string
  email: string | null
  phone: string | null
  home_classroom_id: number | null
  home_classroom: { id: number; display_name: string } | null
}

export function TeachersPage() {
  const qc = useQueryClient()
  const [msg, setMsg] = useState<string | null>(null)
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    phone: '',
    home_classroom_id: '' as string | number,
  })
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)

  const teachersQ = useQuery({
    queryKey: ['teachers'],
    queryFn: () => apiJson<Teacher[]>('/api/teachers/'),
  })
  const roomsQ = useQuery({
    queryKey: ['classrooms'],
    queryFn: () => apiJson<Classroom[]>('/api/classrooms/'),
  })

  const saveM = useMutation({
    mutationFn: async () => {
      const payload = {
        full_name: form.full_name.trim(),
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        home_classroom_id: form.home_classroom_id === '' ? null : Number(form.home_classroom_id),
      }
      if (!payload.full_name) throw new Error('Укажите ФИО')
      if (editingId === 'new') {
        await apiJson<Teacher>('/api/teachers/', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
      } else if (typeof editingId === 'number') {
        await apiJson<Teacher>(`/api/teachers/${editingId}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      }
    },
    onSuccess: async () => {
      setMsg('Сохранено')
      setEditingId(null)
      await qc.invalidateQueries({ queryKey: ['teachers'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  const delM = useMutation({
    mutationFn: (id: number) =>
      apiJson<void>(`/api/teachers/${id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      setMsg('Удалено')
      await qc.invalidateQueries({ queryKey: ['teachers'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  useEffect(() => {
    if (!msg) return
    const t = setTimeout(() => setMsg(null), 4000)
    return () => clearTimeout(t)
  }, [msg])

  function openNew() {
    setForm({ full_name: '', email: '', phone: '', home_classroom_id: '' })
    setEditingId('new')
  }

  function openEdit(t: Teacher) {
    setForm({
      full_name: t.full_name,
      email: t.email ?? '',
      phone: t.phone ?? '',
      home_classroom_id: t.home_classroom_id ?? '',
    })
    setEditingId(t.id)
  }

  if (teachersQ.isLoading || roomsQ.isLoading) return <p>Загрузка…</p>
  if (teachersQ.isError)
    return <p className="text-danger">{(teachersQ.error as Error).message}</p>

  const teachers = teachersQ.data ?? []
  const rooms = roomsQ.data ?? []

  return (
    <div>
      <PageHeader
        title="Учителя"
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
      <div className="table-responsive card shadow-sm">
        <table className="table table-hover mb-0">
          <thead className="table-light">
            <tr>
              <th>ФИО</th>
              <th>Email</th>
              <th>Кабинет</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {teachers.map((t) => (
              <tr key={t.id}>
                <td>{t.full_name}</td>
                <td>{t.email ?? '—'}</td>
                <td>{t.home_classroom?.display_name ?? '—'}</td>
                <td className="text-end text-nowrap">
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-secondary me-1"
                    onClick={() => openEdit(t)}
                  >
                    Изменить
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-danger"
                    onClick={() => {
                      if (confirm(`Удалить «${t.full_name}»?`)) delM.mutate(t.id)
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
        <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,.35)' }}>
          <div className="modal-dialog">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">
                  {editingId === 'new' ? 'Новый учитель' : 'Редактирование'}
                </h5>
                <button type="button" className="btn-close" aria-label="Закрыть" onClick={() => setEditingId(null)} />
              </div>
              <div className="modal-body">
                <div className="mb-2">
                  <label className="form-label">ФИО</label>
                  <input
                    className="form-control"
                    value={form.full_name}
                    onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
                  />
                </div>
                <div className="mb-2">
                  <label className="form-label">Email</label>
                  <input
                    className="form-control"
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                  />
                </div>
                <div className="mb-2">
                  <label className="form-label">Телефон</label>
                  <input
                    className="form-control"
                    value={form.phone}
                    onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                  />
                </div>
                <div className="mb-2">
                  <label className="form-label">Домашний кабинет</label>
                  <select
                    className="form-select"
                    value={form.home_classroom_id === '' ? '' : String(form.home_classroom_id)}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        home_classroom_id: e.target.value === '' ? '' : Number(e.target.value),
                      }))
                    }
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
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={saveM.isPending}
                  onClick={() => saveM.mutate()}
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
