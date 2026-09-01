import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { exportTeacherUrl, fetchTeacherReport } from '../api/reports'
import { PageHeader } from '../components/PageHeader'
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
      <PageHeader
        title={r.teacher_name}
        subtitle="Недельное расписание · звонки и перемены"
        actions={
          <>
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
          </>
        }
      />

      <ReportGrid dayNames={r.day_names} workingDays={r.working_days} rows={rows} />
    </div>
  )
}
