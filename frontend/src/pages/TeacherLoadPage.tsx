import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { listTeacherLoad, type TeacherLoad } from '../api/teachers'
import { PageHeader } from '../components/PageHeader'

function hoursWord(n: number) {
  const n10 = n % 10
  const n100 = n % 100
  if (n10 === 1 && n100 !== 11) return 'час'
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return 'часа'
  return 'часов'
}

type ShiftHoursRow = { key: string; name: string; hours: number }

function shiftHours(row: TeacherLoad): ShiftHoursRow[] {
  const items: ShiftHoursRow[] = row.shifts.map((s) => ({
    key: String(s.id),
    name: s.name,
    hours: s.hours,
  }))
  if (row.unassigned_shift_hours > 0) {
    items.push({ key: 'none', name: 'без смены', hours: row.unassigned_shift_hours })
  }
  return items
}

function matchesQuery(row: TeacherLoad, q: string) {
  if (!q) return true
  const hay = [
    row.full_name,
    ...row.subjects.map((s) => s.subject_name),
    ...shiftHours(row).map((s) => s.name),
  ]
    .join(' ')
    .toLowerCase()
  return hay.includes(q)
}

export function TeacherLoadPage() {
  const [query, setQuery] = useState('')
  const [shiftId, setShiftId] = useState<string>('all')

  const q = useQuery({
    queryKey: ['teachers', 'load'],
    queryFn: listTeacherLoad,
  })

  const rows = q.data ?? []
  const shifts = useMemo(() => {
    const seen = new Map<number, { id: number; name: string }>()
    for (const row of rows) {
      for (const s of row.shifts) {
        if (!seen.has(s.id)) seen.set(s.id, { id: s.id, name: s.name })
      }
    }
    return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name, 'ru'))
  }, [rows])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return rows.filter((row) => {
      if (!matchesQuery(row, needle)) return false
      if (shiftId === 'all') return true
      if (shiftId === 'none') return row.has_classes_without_shift
      return row.shifts.some((s) => String(s.id) === shiftId)
    })
  }, [rows, query, shiftId])

  if (q.isLoading) return <p>Загрузка…</p>
  if (q.isError) return <p className="text-danger">{(q.error as Error).message}</p>

  return (
    <div>
      <PageHeader
        title="Нагрузка учителей"
        subtitle="ФИО, часы в неделю по предметам и сколько часов в каждой смене"
        actions={
          <Link to="/teachers" className="btn btn-outline-secondary">
            Справочник учителей
          </Link>
        }
      />

      <div className="d-flex flex-wrap gap-2 mb-3">
        <input
          className="form-control"
          style={{ maxWidth: 320 }}
          placeholder="Поиск по ФИО, предмету, смене"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          className="form-select"
          style={{ maxWidth: 220 }}
          value={shiftId}
          onChange={(e) => setShiftId(e.target.value)}
        >
          <option value="all">Все смены</option>
          {shifts.map((s) => (
            <option key={s.id} value={String(s.id)}>
              {s.name}
            </option>
          ))}
          <option value="none">Без смены</option>
        </select>
      </div>

      {rows.length === 0 ? (
        <p className="text-muted">
          Нет учителей. Добавьте их в{' '}
          <Link to="/teachers">справочнике</Link> или загрузите нагрузку через{' '}
          <Link to="/import">импорт Excel</Link>.
        </p>
      ) : filtered.length === 0 ? (
        <p className="text-muted">Ничего не найдено.</p>
      ) : (
        <div className="table-responsive card shadow-sm">
          <table className="table table-hover mb-0 align-middle">
            <thead className="table-light">
              <tr>
                <th>ФИО</th>
                <th>Предметы, часы в неделю</th>
                <th>Часы по сменам</th>
                <th className="text-end">Всего</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => {
                const byShift = shiftHours(row)
                return (
                  <tr key={row.id}>
                    <td className="fw-medium text-nowrap">{row.full_name}</td>
                    <td>
                      {row.subjects.length === 0 ? (
                        <span className="text-muted">нет назначений</span>
                      ) : (
                        <div className="d-flex flex-wrap gap-1">
                          {row.subjects.map((s) => (
                            <span
                              key={s.subject_id}
                              className="d-inline-flex align-items-center gap-1 rounded-pill px-2 py-1 small"
                              style={{
                                background: `color-mix(in srgb, ${s.color} 18%, transparent)`,
                                border: `1px solid color-mix(in srgb, ${s.color} 35%, transparent)`,
                              }}
                            >
                              <span
                                aria-hidden
                                style={{
                                  width: 8,
                                  height: 8,
                                  borderRadius: '50%',
                                  background: s.color,
                                  flexShrink: 0,
                                }}
                              />
                              {s.subject_name}
                              <span className="text-muted">
                                {s.hours} {hoursWord(s.hours)}
                              </span>
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td>
                      {byShift.length === 0 ? (
                        <span className="text-muted">—</span>
                      ) : (
                        <div className="d-flex flex-wrap gap-1">
                          {byShift.map((s) => (
                            <span
                              key={s.key}
                              className="d-inline-flex align-items-center gap-1 rounded-pill px-2 py-1 small"
                              style={{
                                border: '1px solid color-mix(in srgb, currentColor 18%, transparent)',
                              }}
                            >
                              {s.name}
                              <span className="text-muted">
                                {s.hours} {hoursWord(s.hours)}
                              </span>
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="text-end text-nowrap">
                      {row.total_hours > 0 ? (
                        <strong>
                          {row.total_hours} {hoursWord(row.total_hours)}
                        </strong>
                      ) : (
                        <span className="text-muted">0</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
