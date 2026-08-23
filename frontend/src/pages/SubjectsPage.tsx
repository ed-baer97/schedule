import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../components/PageHeader'
import { ModalPortal } from '../components/ModalPortal'
import {
  createSubject,
  deleteSubject,
  getColorPalette,
  listSubjects,
  updateSubject,
  updateSubjectColor,
  type Subject,
} from '../api/subjects'
import { listClassrooms } from '../api/classrooms'

const DEFAULT_PALETTE = [
  '#147f78',
  '#c45a42',
  '#c4842e',
  '#0e5c57',
  '#3f5248',
  '#1a6a64',
  '#a65a48',
  '#8b6b3e',
  '#2a403a',
  '#b86b2e',
]

export function SubjectsPage() {
  const qc = useQueryClient()
  const [filter, setFilter] = useState<'all' | 'elementary' | 'secondary'>('all')
  const [msg, setMsg] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [colorPick, setColorPick] = useState<Subject | null>(null)
  const [form, setForm] = useState({
    name: '',
    color: '#147f78',
    requires_fixed_classroom: false,
    default_classroom_id: '',
  })

  const subjectsQ = useQuery({
    queryKey: ['subjects', filter],
    queryFn: () => listSubjects(filter),
  })
  const roomsQ = useQuery({
    queryKey: ['classrooms'],
    queryFn: listClassrooms,
  })
  const paletteQ = useQuery({
    queryKey: ['subjects', 'color-palette'],
    queryFn: getColorPalette,
  })
  const palette = paletteQ.data?.length ? paletteQ.data : DEFAULT_PALETTE

  const colorM = useMutation({
    mutationFn: ({ id, color }: { id: number; color: string }) => updateSubjectColor(id, color),
    onSuccess: async () => {
      setColorPick(null)
      setMsg('Цвет сохранён')
      await qc.invalidateQueries({ queryKey: ['subjects'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  const saveM = useMutation({
    mutationFn: async () => {
      const payload = {
        name: form.name.trim(),
        color: form.color,
        requires_fixed_classroom: form.requires_fixed_classroom,
        default_classroom_id: form.default_classroom_id === '' ? null : Number(form.default_classroom_id),
      }
      if (!payload.name) throw new Error('Укажите название')
      if (editingId === 'new') {
        await createSubject(payload)
      } else if (typeof editingId === 'number') {
        await updateSubject(editingId, payload)
      }
    },
    onSuccess: async () => {
      setMsg('Сохранено')
      setEditingId(null)
      await qc.invalidateQueries({ queryKey: ['subjects'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  const delM = useMutation({
    mutationFn: deleteSubject,
    onSuccess: async () => {
      setMsg('Удалено')
      await qc.invalidateQueries({ queryKey: ['subjects'] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  useEffect(() => {
    if (!msg) return
    const t = setTimeout(() => setMsg(null), 4000)
    return () => clearTimeout(t)
  }, [msg])

  function openNew() {
    setForm({
      name: '',
      color: '#147f78',
      requires_fixed_classroom: false,
      default_classroom_id: '',
    })
    setEditingId('new')
  }

  function openEdit(s: Subject) {
    setForm({
      name: s.name,
      color: s.display_color,
      requires_fixed_classroom: s.requires_fixed_classroom,
      default_classroom_id: s.default_classroom_id === null ? '' : String(s.default_classroom_id),
    })
    setEditingId(s.id)
  }

  if (subjectsQ.isLoading || roomsQ.isLoading) return <p>Загрузка…</p>
  if (subjectsQ.isError) return <p className="text-danger">{(subjectsQ.error as Error).message}</p>

  const subjects = subjectsQ.data ?? []
  const rooms = roomsQ.data ?? []

  return (
    <div>
      <PageHeader
        title="Предметы"
        actions={
          <button type="button" className="btn btn-primary" onClick={openNew}>
            <i className="bi bi-plus-lg me-1" />
            Добавить
          </button>
        }
      />
      <ul className="nav nav-tabs mb-3">
        <li className="nav-item">
          <button type="button" className={`nav-link ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>
            Все
          </button>
        </li>
        <li className="nav-item">
          <button type="button" className={`nav-link ${filter === 'elementary' ? 'active' : ''}`} onClick={() => setFilter('elementary')}>
            НШ (по нагрузке)
          </button>
        </li>
        <li className="nav-item">
          <button type="button" className={`nav-link ${filter === 'secondary' ? 'active' : ''}`} onClick={() => setFilter('secondary')}>
            ОШ (по нагрузке)
          </button>
        </li>
      </ul>
      {msg && <div className="alert alert-info py-2">{msg}</div>}
      <div className="table-responsive card shadow-sm">
        <table className="table table-hover mb-0 align-middle">
          <thead className="table-light">
            <tr>
              <th style={{ width: 48 }} />
              <th>Название</th>
              <th>Фикс. кабинет</th>
              <th>По умолчанию</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {subjects.map((s) => (
              <tr key={s.id}>
                <td>
                  <button
                    type="button"
                    className="d-inline-block rounded border p-0"
                    style={{ width: 24, height: 24, background: s.display_color, borderColor: s.display_color }}
                    title="Нажмите, чтобы выбрать цвет"
                    onClick={() => setColorPick(s)}
                  />
                </td>
                <td>
                  <Link
                    to={`/subjects/${s.id}/assignments${filter === 'all' ? '?school_level=elementary' : `?school_level=${filter}`}`}
                    className="text-decoration-none fw-semibold"
                  >
                    {s.name}
                  </Link>
                </td>
                <td>{s.requires_fixed_classroom ? 'да' : '—'}</td>
                <td>{s.default_classroom?.display_name ?? '—'}</td>
                <td className="text-end text-nowrap">
                  <Link
                    to={`/subjects/${s.id}/assignments${filter === 'all' ? '' : `?school_level=${filter}`}`}
                    className="btn btn-sm btn-outline-primary me-1"
                  >
                    Назначения
                  </Link>
                  <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => openEdit(s)}>
                    Изменить
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-danger"
                    onClick={() => {
                      if (confirm(`Удалить предмет «${s.name}»?`)) delM.mutate(s.id)
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

      {colorPick && (
        <ModalPortal>
        <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,.35)' }}>
          <div className="modal-dialog modal-sm">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">Цвет: {colorPick.name}</h5>
                <button type="button" className="btn-close" onClick={() => setColorPick(null)} aria-label="Закрыть" />
              </div>
              <div className="modal-body">
                <div className="d-flex flex-wrap gap-1 mb-2">
                  {palette.map((c) => (
                    <button
                      key={c}
                      type="button"
                      disabled={colorM.isPending}
                      className={`btn btn-sm p-2 border ${colorPick.display_color === c ? 'border-dark border-2' : ''}`}
                      style={{ background: c }}
                      title={c}
                      onClick={() => colorM.mutate({ id: colorPick.id, color: c })}
                    />
                  ))}
                </div>
                <label className="form-label small text-muted">Свой цвет</label>
                <input
                  type="color"
                  className="form-control form-control-color w-100"
                  defaultValue={colorPick.display_color}
                  disabled={colorM.isPending}
                  onChange={(e) => colorM.mutate({ id: colorPick.id, color: e.target.value })}
                />
              </div>
            </div>
          </div>
        </div>
        </ModalPortal>
      )}

      {editingId !== null && (
        <ModalPortal>
        <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,.35)' }}>
          <div className="modal-dialog">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">{editingId === 'new' ? 'Новый предмет' : 'Редактирование'}</h5>
                <button type="button" className="btn-close" onClick={() => setEditingId(null)} aria-label="Закрыть" />
              </div>
              <div className="modal-body">
                <div className="mb-2">
                  <label className="form-label">Название</label>
                  <input className="form-control" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
                </div>
                <div className="mb-2">
                  <label className="form-label">Цвет</label>
                  <div className="d-flex flex-wrap gap-1 mb-2">
                    {palette.map((c) => (
                      <button
                        key={c}
                        type="button"
                        className={`btn btn-sm p-2 border ${form.color === c ? 'border-dark border-2' : ''}`}
                        style={{ background: c }}
                        title={c}
                        onClick={() => setForm((f) => ({ ...f, color: c }))}
                      />
                    ))}
                  </div>
                  <input type="color" className="form-control form-control-color" value={form.color} onChange={(e) => setForm((f) => ({ ...f, color: e.target.value }))} />
                </div>
                <div className="form-check mb-2">
                  <input
                    className="form-check-input"
                    type="checkbox"
                    checked={form.requires_fixed_classroom}
                    id="reqRoom"
                    onChange={(e) => setForm((f) => ({ ...f, requires_fixed_classroom: e.target.checked }))}
                  />
                  <label className="form-check-label" htmlFor="reqRoom">
                    Нужен фиксированный кабинет
                  </label>
                </div>
                <div className="mb-2">
                  <label className="form-label">Кабинет по умолчанию</label>
                  <select
                    className="form-select"
                    value={form.default_classroom_id}
                    onChange={(e) => setForm((f) => ({ ...f, default_classroom_id: e.target.value }))}
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
