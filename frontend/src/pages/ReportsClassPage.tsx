import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { exportClassUrl, fetchClassReport } from '../api/reports'
import { PageHeader } from '../components/PageHeader'
import {
  ReportGrid,
  buildTimetableRows,
  indexReportCells,
  renderClassReportCells,
} from '../components/ReportGrid'

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
  const rows = buildTimetableRows({
    dayNames: r.day_names,
    workingDays: r.working_days,
    lessonsRange: r.lessons_range,
    classHourDay: r.class_hour_day,
    classHourTimeLabel: r.class_hour_time_label,
    lessonTimesByDay: r.lesson_times_by_day,
    cellsBy: indexReportCells(r.cells),
    renderCells: renderClassReportCells,
  })

  return (
    <div>
      <PageHeader
        title={`Класс ${r.class_name}`}
        subtitle="Недельное расписание · звонки и перемены"
        actions={
          <>
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
          </>
        }
      />

      <ReportGrid dayNames={r.day_names} workingDays={r.working_days} rows={rows} />
    </div>
  )
}
