import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { exportClassUrl, fetchClassReport, type ReportCell } from '../api/reports'

export function ReportsClassPage() {
  const params = useParams()
  const id = Number(params.id)

  const q = useQuery({
    queryKey: ['reports', 'class', id],
    queryFn: () => fetchClassReport(id),
    enabled: !!id,
  })

  if (!id) return <p className="text-danger">Не указан класс</p>
  if (q.isLoading) return <p>Загрузка…</p>
  if (q.isError) return <p className="text-danger">{(q.error as Error).message}</p>
  const r = q.data!

  const cellsBy = new Map<string, ReportCell[]>()
  for (const c of r.cells) {
    const key = `${c.day_of_week}:${c.lesson_number}`
    const arr = cellsBy.get(key) ?? []
    arr.push(c)
    cellsBy.set(key, arr)
  }

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3 no-print">
        <h1 className="h3 mb-0">Расписание класса {r.class_name}</h1>
        <div className="d-flex gap-2">
          <a href={exportClassUrl(r.class_id)} className="btn btn-success btn-sm">
            Скачать Excel
          </a>
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm"
            onClick={() => window.print()}
          >
            Печать
          </button>
          <Link to="/reports" className="btn btn-outline-secondary btn-sm">
            ← Отчёты
          </Link>
        </div>
      </div>

      <div className="card">
        <div className="table-responsive">
          <table className="table table-bordered mb-0" style={{ fontSize: '0.85rem' }}>
            <thead className="table-light">
              <tr>
                <th style={{ width: 110 }}>Урок</th>
                {r.day_names.slice(0, r.working_days).map((d, i) => (
                  <th key={i} className="text-center">{d}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {r.class_hour_day != null && r.class_hour_time_label && (
                <tr>
                  <td className="text-center align-middle">
                    <div className="fw-bold">Классный час</div>
                    <div className="small text-muted text-nowrap">{r.class_hour_time_label}</div>
                  </td>
                  {r.day_names.slice(0, r.working_days).map((_, dayIdx) => {
                    const day = dayIdx + 1
                    if (day !== r.class_hour_day) return <td key={dayIdx} />
                    const matches = cellsBy.get(`${day}:0`) ?? []
                    return <td key={dayIdx}>{renderCells(matches)}</td>
                  })}
                </tr>
              )}
              {r.lessons_range.map((lesson) => (
                <tr key={lesson}>
                  <td className="text-center align-middle">
                    <div className="fw-bold">{lesson}</div>
                  </td>
                  {r.day_names.slice(0, r.working_days).map((_, dayIdx) => {
                    const day = dayIdx + 1
                    const matches = cellsBy.get(`${day}:${lesson}`) ?? []
                    const time = r.lesson_times_by_day[day]?.[lesson]
                    return (
                      <td key={dayIdx}>
                        {time && <div className="small text-muted">{time}</div>}
                        {renderCells(matches)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function renderCells(cells: ReportCell[]) {
  if (cells.length === 0) return null
  return cells.map((c, i) => (
    <div
      key={c.id}
      className="border rounded p-1 mb-1"
      style={{ background: 'white', borderColor: c.subject_color, borderWidth: 2 }}
    >
      {i > 0 && <hr className="my-1" />}
      <div className="fw-semibold" style={{ color: c.subject_color }}>
        {c.subject_name}
        {c.group_number != null && (
          <span className="badge bg-warning text-dark ms-1">гр.{c.group_number}</span>
        )}
      </div>
      <div className="small">{c.teacher_name ?? '?'}</div>
      {c.classroom_name && (
        <div className="small text-muted">каб. {c.classroom_name}</div>
      )}
    </div>
  ))
}
