import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { apiJson } from '../api/client'

type ReportCell = {
  id: number
  day_of_week: number
  lesson_number: number
  subject_name: string
  subject_color: string
  teacher_name: string | null
  class_name: string
  classroom_name: string | null
  group_number: number | null
}

type TeacherReport = {
  teacher_id: number
  teacher_name: string
  day_names: string[]
  working_days: number
  max_lessons: number
  cells: ReportCell[]
}

export function ReportsTeacherPage() {
  const params = useParams()
  const id = Number(params.id)

  const q = useQuery({
    queryKey: ['reports', 'teacher', id],
    queryFn: () => apiJson<TeacherReport>(`/api/reports/teacher/${id}`),
    enabled: !!id,
  })

  if (!id) return <p className="text-danger">Не указан учитель</p>
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
        <h1 className="h3 mb-0">Расписание: {r.teacher_name}</h1>
        <div className="d-flex gap-2">
          <a
            href={`/api/reports/export/teacher/${r.teacher_id}`}
            className="btn btn-success btn-sm"
          >
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
                <th style={{ width: 80 }}>Урок</th>
                {r.day_names.slice(0, r.working_days).map((d, i) => (
                  <th key={i} className="text-center">{d}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: r.max_lessons }, (_, i) => i + 1).map((lesson) => (
                <tr key={lesson}>
                  <td className="text-center fw-bold align-middle">{lesson}</td>
                  {r.day_names.slice(0, r.working_days).map((_, dayIdx) => {
                    const day = dayIdx + 1
                    const matches = cellsBy.get(`${day}:${lesson}`) ?? []
                    return (
                      <td key={dayIdx}>
                        {matches.map((c, i) => (
                          <div
                            key={c.id}
                            className="border rounded p-1 mb-1"
                            style={{
                              background: 'white',
                              borderColor: c.subject_color,
                              borderWidth: 2,
                            }}
                          >
                            {i > 0 && <hr className="my-1" />}
                            <div className="fw-semibold" style={{ color: c.subject_color }}>
                              {c.class_name}
                            </div>
                            <div className="small">{c.subject_name}</div>
                            {c.classroom_name && (
                              <div className="small text-muted">каб. {c.classroom_name}</div>
                            )}
                          </div>
                        ))}
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
