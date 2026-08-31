import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { exportTeacherUrl, fetchTeacherReport } from '../api/reports'
import {
  ReportGrid,
  buildTimetableRows,
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
  const lessonsRange =
    r.lessons_range?.length > 0
      ? r.lessons_range
      : Array.from({ length: r.max_lessons }, (_, i) => i + 1)

  const rows = buildTimetableRows({
    dayNames: r.day_names,
    workingDays: r.working_days,
    lessonsRange,
    classHourDay: r.class_hour_day,
    classHourTimeLabel: r.class_hour_time_label,
    lessonTimesByDay: r.lesson_times_by_day,
    cellsBy: indexReportCells(r.cells),
    renderCells: renderTeacherReportCells,
  })

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

      <ReportGrid
        dayNames={r.day_names}
        workingDays={r.working_days}
        headerWidth={120}
        rows={rows}
      />
    </div>
  )
}
