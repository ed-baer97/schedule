import type { CSSProperties, ReactNode } from 'react'
import type { ReportCell } from '../api/reports'

type ReportGridProps = {
  dayNames: string[]
  workingDays: number
  headerWidth?: number
  /** Rows: first cell is lesson label; then one cell per day. */
  rows: Array<{ key: string | number; label: ReactNode; dayCells: ReactNode[] }>
}

export function ReportGrid(props: ReportGridProps) {
  const { dayNames, workingDays, headerWidth = 120, rows } = props
  return (
    <div className="card">
      <div className="table-responsive">
        <table
          className="table table-bordered mb-0 report-grid-table"
          style={{ fontSize: '0.85rem' }}
        >
          <thead className="table-light">
            <tr>
              <th style={{ width: headerWidth }}>Урок</th>
              {dayNames.slice(0, workingDays).map((d, i) => (
                <th key={i} className="text-center">
                  {d}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td className="text-center align-middle report-lesson-index">{row.label}</td>
                {row.dayCells.map((cell, i) => (
                  <td key={i} className="align-top">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function indexReportCells(cells: ReportCell[]) {
  const cellsBy = new Map<string, ReportCell[]>()
  for (const c of cells) {
    const key = `${c.day_of_week}:${c.lesson_number}`
    const arr = cellsBy.get(key) ?? []
    arr.push(c)
    cellsBy.set(key, arr)
  }
  return cellsBy
}

/** JSON object keys are strings; accept both number and string lookup. */
export function reportLessonTime(
  times: Record<number, Record<number, string>> | undefined,
  day: number,
  lesson: number,
): string | undefined {
  if (!times) return undefined
  const raw = times as Record<string | number, Record<string | number, string>>
  const byDay = raw[day] ?? raw[String(day)]
  if (!byDay) return undefined
  return byDay[lesson] ?? byDay[String(lesson)]
}

export function firstLessonTime(
  times: Record<number, Record<number, string>> | undefined,
  workingDays: number,
  lesson: number,
): string | undefined {
  if (!times) return undefined
  for (let day = 1; day <= workingDays; day += 1) {
    const t = reportLessonTime(times, day, lesson)
    if (t) return t
  }
  const lessonKey = String(lesson)
  for (const byDay of Object.values(times)) {
    if (!byDay || typeof byDay !== 'object') continue
    const row = byDay as Record<string | number, string>
    const t = row[lesson] ?? row[lessonKey]
    if (t) return t
  }
  return undefined
}

function splitBellLabel(label: string): [string, string] | null {
  const idx = label.search(/[–—-]/)
  if (idx <= 0) return null
  const start = label.slice(0, idx).trim()
  const end = label.slice(idx + 1).trim()
  if (!start || !end) return null
  return [start, end]
}

export function ReportBell({ time }: { time: string }) {
  const parts = splitBellLabel(time)
  return (
    <div className="report-bell" title={`Звонок ${time}`}>
      {parts ? (
        <>
          <span>{parts[0]}</span>
          <span className="report-bell-dash" aria-hidden>
            –
          </span>
          <span>{parts[1]}</span>
        </>
      ) : (
        <span>{time}</span>
      )}
    </div>
  )
}

export function buildTimetableRows(opts: {
  dayNames: string[]
  workingDays: number
  lessonsRange: number[]
  classHourDay: number | null | undefined
  classHourTimeLabel: string | null | undefined
  lessonTimesByDay: Record<number, Record<number, string>> | undefined
  cellsBy: Map<string, ReportCell[]>
  renderCells: (cells: ReportCell[]) => ReactNode
}): ReportGridProps['rows'] {
  const {
    dayNames,
    workingDays,
    lessonsRange,
    classHourDay,
    classHourTimeLabel,
    lessonTimesByDay,
    cellsBy,
    renderCells,
  } = opts
  const days = dayNames.slice(0, workingDays)
  const rows: ReportGridProps['rows'] = []

  if (classHourDay != null || classHourTimeLabel) {
    rows.push({
      key: 'class-hour',
      label: (
        <>
          <div className="fw-bold">Кл. час</div>
          {classHourTimeLabel ? <ReportBell time={classHourTimeLabel} /> : null}
        </>
      ),
      dayCells: days.map((_, dayIdx) => {
        const day = dayIdx + 1
        if (classHourDay != null && day !== classHourDay) return null
        if (classHourDay == null) return null
        return renderCells(cellsBy.get(`${day}:0`) ?? [])
      }),
    })
  }

  for (const lesson of lessonsRange) {
    const time = firstLessonTime(lessonTimesByDay, workingDays, lesson)
    rows.push({
      key: lesson,
      label: (
        <>
          <div className="fw-bold report-lesson-num">{lesson}</div>
          {time ? <ReportBell time={time} /> : null}
        </>
      ),
      dayCells: days.map((_, dayIdx) => {
        const day = dayIdx + 1
        return renderCells(cellsBy.get(`${day}:${lesson}`) ?? [])
      }),
    })
  }
  return rows
}

function lessonCardStyle(color: string): CSSProperties {
  return { ['--lesson-color' as string]: color }
}

export function renderClassReportCells(cells: ReportCell[]) {
  if (cells.length === 0) return null
  return cells.map((c) => (
    <div key={c.id} className="lesson-card report-lesson-card" style={lessonCardStyle(c.subject_color)}>
      <div className="lesson-subject">
        {c.subject_name}
        {c.group_number != null && (
          <>
            {' '}
            <span className="badge schedule-group-badge">гр.{c.group_number}</span>
          </>
        )}
      </div>
      <div className="lesson-card-meta">
        <span className="teacher-name">{c.teacher_name ?? '—'}</span>
        <span className="lesson-room">каб. {c.classroom_name ?? '—'}</span>
      </div>
    </div>
  ))
}

export function renderTeacherReportCells(cells: ReportCell[]) {
  if (cells.length === 0) return null
  return cells.map((c) => (
    <div key={c.id} className="lesson-card report-lesson-card" style={lessonCardStyle(c.subject_color)}>
      <div className="lesson-subject">{c.class_name}</div>
      <div className="lesson-card-meta">
        <span className="teacher-name">{c.subject_name}</span>
        <span className="lesson-room">каб. {c.classroom_name ?? '—'}</span>
      </div>
    </div>
  ))
}
