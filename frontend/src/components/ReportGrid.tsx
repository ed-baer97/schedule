import type { ReactNode } from 'react'
import type { ReportCell } from '../api/reports'

type ReportGridProps = {
  dayNames: string[]
  workingDays: number
  headerWidth?: number
  /** Rows: first cell is lesson label; then one cell per day. */
  rows: Array<{ key: string | number; label: ReactNode; dayCells: ReactNode[] }>
}

export function ReportGrid(props: ReportGridProps) {
  const { dayNames, workingDays, headerWidth = 80, rows } = props
  return (
    <div className="card">
      <div className="table-responsive">
        <table className="table table-bordered mb-0" style={{ fontSize: '0.85rem' }}>
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
                <td className="text-center align-middle">{row.label}</td>
                {row.dayCells.map((cell, i) => (
                  <td key={i}>{cell}</td>
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

export function renderClassReportCells(cells: ReportCell[]) {
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

export function renderTeacherReportCells(cells: ReportCell[]) {
  if (cells.length === 0) return null
  return cells.map((c, i) => (
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
  ))
}
