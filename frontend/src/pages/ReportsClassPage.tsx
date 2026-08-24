import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { exportClassUrl, fetchClassReport } from '../api/reports'
import {
  ReportGrid,
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
  const cellsBy = indexReportCells(r.cells)

  const rows = [
    ...(r.class_hour_day != null && r.class_hour_time_label
      ? [
          {
            key: 'class-hour',
            label: (
              <>
                <div className="fw-bold">Классный час</div>
                <div className="small text-muted text-nowrap">{r.class_hour_time_label}</div>
              </>
            ),
            dayCells: r.day_names.slice(0, r.working_days).map((_, dayIdx) => {
              const day = dayIdx + 1
              if (day !== r.class_hour_day) return null
              return renderClassReportCells(cellsBy.get(`${day}:0`) ?? [])
            }),
          },
        ]
      : []),
    ...r.lessons_range.map((lesson) => ({
      key: lesson,
      label: <div className="fw-bold">{lesson}</div>,
      dayCells: r.day_names.slice(0, r.working_days).map((_, dayIdx) => {
        const day = dayIdx + 1
        const matches = cellsBy.get(`${day}:${lesson}`) ?? []
        const time = r.lesson_times_by_day[day]?.[lesson]
        return (
          <>
            {time && <div className="small text-muted">{time}</div>}
            {renderClassReportCells(matches)}
          </>
        )
      }),
    })),
  ]

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

      <ReportGrid
        dayNames={r.day_names}
        workingDays={r.working_days}
        headerWidth={110}
        rows={rows}
      />
    </div>
  )
}
