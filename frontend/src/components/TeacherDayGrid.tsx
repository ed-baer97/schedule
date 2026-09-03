import type { TeacherDayData, TeacherDayLesson, TeacherDayOccupant } from '../api/schedule'

function occupantLabel(occ: TeacherDayOccupant) {
  const bits = [occ.class_name, occ.subject_name]
  if (occ.group_number != null) bits.push(`гр.${occ.group_number}`)
  return bits.join(' · ')
}

function occupantTitle(occ: TeacherDayOccupant) {
  const bits = [occupantLabel(occ)]
  if (occ.classroom_name) bits.push(`каб. ${occ.classroom_name}`)
  return bits.join(' · ')
}

function lessonNum(lesson: number) {
  return lesson === 0 ? 'КЧ' : String(lesson)
}

function rowClass(row: TeacherDayLesson) {
  const bits = ['teacher-day-row']
  if (row.is_candidate) bits.push('is-candidate')
  if (row.is_gap) bits.push('is-gap')
  if (row.overlaps_current) bits.push('is-overlap')
  if (row.occupants.length) bits.push('is-occupied')
  return bits.join(' ')
}

function cellBody(row: TeacherDayLesson) {
  if (row.occupants.length) {
    return row.occupants.map((occ) => (
      <span
        key={`${occ.class_id}-${occ.subject_name}-${occ.group_number ?? 0}`}
        className="teacher-day-chip"
        style={{ ['--lesson-color' as string]: occ.subject_color }}
        title={occupantTitle(occ)}
      >
        {occ.class_name}
      </span>
    ))
  }
  if (row.is_candidate && row.is_gap) return 'сюда · окно'
  if (row.is_candidate) return 'сюда'
  if (row.is_gap) return 'окно'
  return '—'
}

export function TeacherDayGrid(props: {
  data: TeacherDayData | undefined
  loading: boolean
  error: string | null
}) {
  const { data, loading, error } = props
  if (loading) {
    return <div className="teacher-day-grid text-muted small">День учителя…</div>
  }
  if (error) {
    return <div className="teacher-day-grid text-danger small">{error}</div>
  }
  if (!data) return null
  if (data.shifts.length === 0) {
    return (
      <div className="teacher-day-grid">
        <div className="teacher-day-grid-title">День учителя · {data.day_name}</div>
        <div className="teacher-day-grid-note">В этот день уроков нет.</div>
      </div>
    )
  }

  return (
    <div className="teacher-day-grid">
      <div className="teacher-day-grid-title">День учителя · {data.day_name}</div>
      {data.other_shift_gap ? (
        <div className="teacher-day-grid-note">{data.other_shift_gap}</div>
      ) : null}
      <div className="teacher-day-grid-shifts">
        {data.shifts.map((shift) => (
          <div
            key={shift.shift_id ?? 'none'}
            className={`teacher-day-shift${shift.is_current ? ' is-current' : ' is-other'}`}
          >
            <div className="teacher-day-shift-head" title={shift.shift_name}>
              {shift.shift_name}
              {shift.is_current ? ' · эта' : ''}
            </div>
            {shift.lessons.map((row) => (
              <div key={`${shift.shift_id ?? 'none'}-${row.lesson}`} className={rowClass(row)}>
                <span className="teacher-day-num">{lessonNum(row.lesson)}</span>
                <span className="teacher-day-time">{row.time_label ?? ''}</span>
                <span className="teacher-day-body">{cellBody(row)}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
