import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { exportTeacherUrl, fetchTeacherReport } from '../api/reports'
import {
  ReportGrid,
  indexReportCells,
  renderTeacherReportCells,
} from '../components/ReportGrid'

export function ReportsTeacherPage() {
  const params = useParams()
  const id = Number(params.id)

  const q = useQuery({
    queryKey: ['reports', 'teacher', id],
    queryFn: () => fetchTeacherReport(id),
    enabled: !!id,
  })

  if (!id) return <p className="text-danger">Не указан учитель</p>
  if (q.isLoading) return <p>Загрузка…</p>
  if (q.isError) return <p className="text-danger">{(q.error as Error).message}</p>
  const r = q.data!
  const cellsBy = indexReportCells(r.cells)

  const rows = Array.from({ length: r.max_lessons }, (_, i) => i + 1).map((lesson) => ({
    key: lesson,
    label: <span className="fw-bold">{lesson}</span>,
    dayCells: r.day_names.slice(0, r.working_days).map((_, dayIdx) => {
      const day = dayIdx + 1
      return renderTeacherReportCells(cellsBy.get(`${day}:${lesson}`) ?? [])
    }),
  }))

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3 no-print">
        <h1 className="h3 mb-0">Расписание: {r.teacher_name}</h1>
        <div className="d-flex gap-2">
          <a href={exportTeacherUrl(r.teacher_id)} className="btn btn-success btn-sm">
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

      <ReportGrid dayNames={r.day_names} workingDays={r.working_days} rows={rows} />
    </div>
  )
}
