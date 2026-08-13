import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { apiJson } from '../api/client'

type ClassBrief = { id: number; name: string; grade: number }
type SubjectBrief = { id: number; name: string }
type Cell = { class_id: number; subject_id: number; hours: number }
type WorkloadData = {
  school_level: string
  classes: ClassBrief[]
  subjects: SubjectBrief[]
  cells: Cell[]
}

export function WorkloadPage() {
  const qc = useQueryClient()
  const [level, setLevel] = useState<'elementary' | 'secondary'>('elementary')
  const [msg, setMsg] = useState<string | null>(null)

  const q = useQuery({
    queryKey: ['workload', level],
    queryFn: () => apiJson<WorkloadData>(`/api/workload/?school_level=${level}`),
  })

  const cellMap = useMemo(() => {
    const m = new Map<string, number>()
    for (const c of q.data?.cells ?? []) {
      m.set(`${c.class_id}:${c.subject_id}`, c.hours)
    }
    return m
  }, [q.data])

  const saveM = useMutation({
    mutationFn: async (p: { class_id: number; subject_id: number; hours: number }) => {
      await apiJson('/api/workload/cell', {
        method: 'PUT',
        body: JSON.stringify(p),
      })
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['workload', level] })
    },
    onError: (e: Error) => setMsg(e.message),
  })

  if (q.isLoading) return <p>Загрузка…</p>
  if (q.isError) return <p className="text-danger">{(q.error as Error).message}</p>

  const data = q.data!
  const classes = data.classes
  const subjects = data.subjects

  return (
    <div>
      <h1 className="h3 mb-3">Часы (нагрузка)</h1>
      {msg && <div className="alert alert-danger py-2">{msg}</div>}
      <ul className="nav nav-tabs mb-3">
        <li className="nav-item">
          <button type="button" className={`nav-link ${level === 'elementary' ? 'active' : ''}`} onClick={() => setLevel('elementary')}>
            Начальная школа
          </button>
        </li>
        <li className="nav-item">
          <button type="button" className={`nav-link ${level === 'secondary' ? 'active' : ''}`} onClick={() => setLevel('secondary')}>
            Основная школа
          </button>
        </li>
      </ul>
      <p className="text-muted small">
        Часы для пары «класс — предмет» (как в Flask: сначала часы без учителя). Изменение сохраняется при уходе с поля.
      </p>
      {classes.length === 0 || subjects.length === 0 ? (
        <p className="text-muted">Нет классов или предметов для отображения.</p>
      ) : (
        <div className="table-responsive card shadow-sm" style={{ maxHeight: '70vh', overflow: 'auto' }}>
          <table className="table table-bordered table-sm mb-0 text-center" style={{ fontSize: '0.85rem' }}>
            <thead className="table-light sticky-top">
              <tr>
                <th className="text-start">Класс / предмет</th>
                {subjects.map((s) => (
                  <th key={s.id} className="text-nowrap" title={s.name}>
                    {s.name.length > 10 ? `${s.name.slice(0, 9)}…` : s.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {classes.map((cl) => (
                <tr key={cl.id}>
                  <td className="text-start fw-medium text-nowrap">
                    {cl.name} <span className="text-muted">({cl.grade})</span>
                  </td>
                  {subjects.map((su) => {
                    const key = `${cl.id}:${su.id}`
                    const hours = cellMap.get(key) ?? 0
                    return (
                      <td key={su.id} className="p-1">
                        <input
                          className="form-control form-control-sm text-center px-1"
                          style={{ width: 52, minWidth: 52 }}
                          type="number"
                          min={0}
                          defaultValue={hours}
                          key={`${key}-${q.dataUpdatedAt}`}
                          onBlur={(e) => {
                            const v = Number(e.target.value)
                            if (Number.isNaN(v) || v < 0) return
                            if (v !== hours) {
                              setMsg(null)
                              saveM.mutate({ class_id: cl.id, subject_id: su.id, hours: v })
                            }
                          }}
                        />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
