import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchWorkload, updateWorkloadCell, type WorkloadData } from '../api/workload'
import type { SchoolLevel } from '../domain/schoolLevel'

type CellKey = string
type CellStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error'

function cellKey(classId: number, subjectId: number): CellKey {
  return `${classId}:${subjectId}`
}

function parseHours(raw: string): number | null {
  const v = Number(raw)
  if (Number.isNaN(v) || v < 0 || !Number.isInteger(v)) return null
  return v
}

export function WorkloadPage() {
  const qc = useQueryClient()
  const [level, setLevel] = useState<SchoolLevel>('elementary')
  const [drafts, setDrafts] = useState<Record<CellKey, string>>({})
  const [status, setStatus] = useState<Record<CellKey, CellStatus>>({})
  const [banner, setBanner] = useState<{ kind: 'success' | 'danger'; text: string } | null>(
    null,
  )
  const savedTimers = useRef<Map<CellKey, number>>(new Map())
  const draftsRef = useRef(drafts)
  const statusRef = useRef(status)
  draftsRef.current = drafts
  statusRef.current = status

  const q = useQuery({
    queryKey: ['workload', level],
    queryFn: () => fetchWorkload(level),
  })

  const serverHours = useMemo(() => {
    const m = new Map<CellKey, number>()
    for (const c of q.data?.cells ?? []) {
      m.set(cellKey(c.class_id, c.subject_id), c.hours)
    }
    return m
  }, [q.data])

  // Sync drafts from server when data arrives / level changes, without wiping
  // cells the user is mid-edit (dirty/saving/error).
  useEffect(() => {
    if (!q.data) return
    const hours = new Map<CellKey, number>()
    for (const c of q.data.cells) {
      hours.set(cellKey(c.class_id, c.subject_id), c.hours)
    }
    setDrafts((prev) => {
      const next: Record<CellKey, string> = {}
      for (const cl of q.data.classes) {
        for (const su of q.data.subjects) {
          const key = cellKey(cl.id, su.id)
          const st = statusRef.current[key]
          if (st === 'dirty' || st === 'saving' || st === 'error') {
            next[key] = prev[key] ?? String(hours.get(key) ?? 0)
          } else {
            next[key] = String(hours.get(key) ?? 0)
          }
        }
      }
      return next
    })
  }, [q.data, q.dataUpdatedAt, level])

  useEffect(() => {
    return () => {
      for (const t of savedTimers.current.values()) window.clearTimeout(t)
      savedTimers.current.clear()
    }
  }, [])

  useEffect(() => {
    if (!banner || banner.kind !== 'success') return
    const t = window.setTimeout(() => setBanner(null), 2500)
    return () => window.clearTimeout(t)
  }, [banner])

  const saveM = useMutation({
    mutationFn: updateWorkloadCell,
    onMutate: (p) => {
      const key = cellKey(p.class_id, p.subject_id)
      setStatus((s) => ({ ...s, [key]: 'saving' }))
      setBanner(null)
    },
    onSuccess: async (_void, p) => {
      const key = cellKey(p.class_id, p.subject_id)
      qc.setQueryData<WorkloadData>(['workload', level], (old) => {
        if (!old) return old
        const cells = old.cells.filter(
          (c) => !(c.class_id === p.class_id && c.subject_id === p.subject_id),
        )
        if (p.hours > 0) {
          cells.push({
            class_id: p.class_id,
            subject_id: p.subject_id,
            hours: p.hours,
          })
        }
        return { ...old, cells }
      })
      setDrafts((d) => ({ ...d, [key]: String(p.hours) }))
      setStatus((s) => ({ ...s, [key]: 'saved' }))
      setBanner({ kind: 'success', text: 'Часы сохранены' })
      void qc.invalidateQueries({ queryKey: ['subject-assignments'] })
      void qc.invalidateQueries({ queryKey: ['schedule'] })

      const prevTimer = savedTimers.current.get(key)
      if (prevTimer) window.clearTimeout(prevTimer)
      savedTimers.current.set(
        key,
        window.setTimeout(() => {
          setStatus((s) => (s[key] === 'saved' ? { ...s, [key]: 'idle' } : s))
          savedTimers.current.delete(key)
        }, 1600),
      )
    },
    onError: (e: Error, p) => {
      const key = cellKey(p.class_id, p.subject_id)
      const cached = qc.getQueryData<WorkloadData>(['workload', level])
      const server =
        cached?.cells.find(
          (c) => c.class_id === p.class_id && c.subject_id === p.subject_id,
        )?.hours ?? 0
      setDrafts((d) => ({ ...d, [key]: String(server) }))
      setStatus((s) => ({ ...s, [key]: 'error' }))
      setBanner({ kind: 'danger', text: e.message || 'Не удалось сохранить часы' })
    },
  })

  function commitCell(classId: number, subjectId: number) {
    const key = cellKey(classId, subjectId)
    if (status[key] === 'saving') return
    const parsed = parseHours(draftsRef.current[key] ?? '')
    if (parsed === null) {
      const server = serverHours.get(key) ?? 0
      setDrafts((d) => ({ ...d, [key]: String(server) }))
      setStatus((s) => ({ ...s, [key]: 'error' }))
      setBanner({ kind: 'danger', text: 'Введите целое число ≥ 0' })
      return
    }
    const server = serverHours.get(key) ?? 0
    if (parsed === server) {
      setDrafts((d) => ({ ...d, [key]: String(server) }))
      setStatus((s) => ({ ...s, [key]: 'idle' }))
      return
    }
    saveM.mutate({ class_id: classId, subject_id: subjectId, hours: parsed })
  }

  if (q.isLoading) return <p>Загрузка…</p>
  if (q.isError) return <p className="text-danger">{(q.error as Error).message}</p>

  const data = q.data!
  const classes = data.classes
  const subjects = data.subjects

  return (
    <div>
      <h1 className="h3 mb-3">Часы (нагрузка)</h1>
      {banner && (
        <div className={`alert alert-${banner.kind} py-2`}>{banner.text}</div>
      )}
      <ul className="nav nav-tabs mb-3">
        <li className="nav-item">
          <button
            type="button"
            className={`nav-link ${level === 'elementary' ? 'active' : ''}`}
            onClick={() => {
              setLevel('elementary')
              setDrafts({})
              setStatus({})
              setBanner(null)
            }}
          >
            Начальная школа
          </button>
        </li>
        <li className="nav-item">
          <button
            type="button"
            className={`nav-link ${level === 'secondary' ? 'active' : ''}`}
            onClick={() => {
              setLevel('secondary')
              setDrafts({})
              setStatus({})
              setBanner(null)
            }}
          >
            Основная школа
          </button>
        </li>
      </ul>
      <p className="text-muted small">
        Часы предмета у класса за неделю. Подгруппы не складываются: 2 часа — это 2 урока в
        сетке, оба учителя ведут их параллельно. Сохранение: уход с поля или Enter. Жёлтая
        рамка — не сохранено, синяя — сохраняется, зелёная — записано.
      </p>
      {classes.length === 0 || subjects.length === 0 ? (
        <p className="text-muted">Нет классов или предметов для отображения.</p>
      ) : (
        <div
          className="table-responsive card shadow-sm"
          style={{ maxHeight: '70vh', overflow: 'auto' }}
        >
          <table
            className="table table-bordered table-sm mb-0 text-center workload-table"
            style={{ fontSize: '0.85rem' }}
          >
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
                    const key = cellKey(cl.id, su.id)
                    const st = status[key] ?? 'idle'
                    const value = drafts[key] ?? String(serverHours.get(key) ?? 0)
                    return (
                      <td key={su.id} className="p-1">
                        <input
                          className={`form-control form-control-sm text-center px-1 workload-cell is-${st}`}
                          style={{ width: 52, minWidth: 52 }}
                          type="number"
                          min={0}
                          step={1}
                          inputMode="numeric"
                          value={value}
                          disabled={st === 'saving'}
                          aria-busy={st === 'saving'}
                          title={
                            st === 'dirty'
                              ? 'Не сохранено — Tab/Enter или клик вне поля'
                              : st === 'saving'
                                ? 'Сохранение…'
                                : st === 'saved'
                                  ? 'Сохранено'
                                  : st === 'error'
                                    ? 'Ошибка — значение откатили'
                                    : undefined
                          }
                          onChange={(e) => {
                            const raw = e.target.value
                            setDrafts((d) => ({ ...d, [key]: raw }))
                            const parsed = parseHours(raw)
                            const server = serverHours.get(key) ?? 0
                            if (parsed === null || parsed !== server) {
                              setStatus((s) => ({ ...s, [key]: 'dirty' }))
                            } else {
                              setStatus((s) => ({ ...s, [key]: 'idle' }))
                            }
                          }}
                          onBlur={() => commitCell(cl.id, su.id)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault()
                              ;(e.target as HTMLInputElement).blur()
                            }
                            if (e.key === 'Escape') {
                              e.preventDefault()
                              const server = serverHours.get(key) ?? 0
                              setDrafts((d) => ({ ...d, [key]: String(server) }))
                              setStatus((s) => ({ ...s, [key]: 'idle' }))
                              ;(e.target as HTMLInputElement).blur()
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
