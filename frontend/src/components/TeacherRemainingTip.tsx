import { useQuery } from '@tanstack/react-query'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { extractApiError } from '../api/client'
import { fetchTeacherDay, type TeacherRemaining, type TeacherRemainingClass } from '../api/schedule'
import { TeacherDayGrid } from './TeacherDayGrid'

function lessonsWord(n: number) {
  const n10 = n % 10
  const n100 = n % 100
  if (n10 === 1 && n100 !== 11) return 'урок'
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return 'урока'
  return 'уроков'
}

function subjectLabel(subject: TeacherRemainingClass['subjects'][number]) {
  const name =
    subject.group_number != null
      ? `${subject.subject_name} гр.${subject.group_number}`
      : subject.subject_name
  return `${name} ${subject.remaining_hours}`
}

function classLine(row: TeacherRemainingClass) {
  const details = row.subjects.map(subjectLabel).join(', ')
  return details ? `${row.class_name} — ${row.remaining_hours} (${details})` : `${row.class_name} — ${row.remaining_hours}`
}

function parseTeacherId(key: string | null) {
  if (!key?.startsWith('id-')) return null
  const n = Number(key.slice(3))
  return Number.isFinite(n) ? n : null
}

function parseSlot(slotId: string | null) {
  if (!slotId) return null
  const m = /^slot-(\d+)-(\d+)-(\d+)$/.exec(slotId)
  if (!m) return null
  return { classId: Number(m[1]), day: Number(m[2]), lesson: Number(m[3]) }
}

function cssEscape(value: string) {
  return typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(value) : value
}

function rectsOverlap(a: DOMRectReadOnly, b: DOMRectReadOnly) {
  return (
    a.width > 0 &&
    a.height > 0 &&
    b.width > 0 &&
    b.height > 0 &&
    a.left < b.right &&
    a.right > b.left &&
    a.top < b.bottom &&
    a.bottom > b.top
  )
}

function hoverCellEl(card: Element, slotId: string, teacherKey: string | null) {
  const escSlot = cssEscape(slotId)
  if (teacherKey) {
    const match = card.querySelector(
      `.lesson-card[data-slot-id="${escSlot}"][data-teacher-key="${cssEscape(teacherKey)}"]`,
    )
    if (match instanceof HTMLElement) return match
  }
  const anyCard = card.querySelector(`.lesson-card[data-slot-id="${escSlot}"]`)
  if (anyCard instanceof HTMLElement) return anyCard
  const td = card.querySelector(`#${escSlot}`)
  return td instanceof HTMLElement ? td : null
}

type DayParams = {
  teacherId: number
  classId: number
  day: number
  lesson: number
}

export function TeacherRemainingTip({
  remainingByKey,
}: {
  remainingByKey: Map<string, TeacherRemaining>
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [key, setKey] = useState<string | null>(null)
  const [slotId, setSlotId] = useState<string | null>(null)
  const [dayParams, setDayParams] = useState<DayParams | null>(null)
  const [overCell, setOverCell] = useState(false)

  useEffect(() => {
    const card = hostRef.current?.closest('.schedule-grid-card')
    if (!card) return

    const sync = () => {
      setKey(card.getAttribute('data-hover-teacher'))
      setSlotId(card.getAttribute('data-hover-slot'))
    }
    sync()
    const obs = new MutationObserver(sync)
    obs.observe(card, {
      attributes: true,
      attributeFilter: ['data-hover-teacher', 'data-hover-slot'],
    })
    return () => obs.disconnect()
  }, [])

  useEffect(() => {
    const teacherId = parseTeacherId(key)
    const slot = parseSlot(slotId)
    if (teacherId == null || !slot) {
      setDayParams(null)
      return
    }
    const t = window.setTimeout(() => {
      setDayParams({ teacherId, ...slot })
    }, 80)
    return () => window.clearTimeout(t)
  }, [key, slotId])

  const teacherDayQ = useQuery({
    queryKey: [
      'schedule',
      'teacher-day',
      dayParams?.teacherId,
      dayParams?.classId,
      dayParams?.day,
      dayParams?.lesson,
    ],
    queryFn: () =>
      fetchTeacherDay({
        teacherId: dayParams!.teacherId,
        day: dayParams!.day,
        classId: dayParams!.classId,
        lesson: dayParams!.lesson,
      }),
    enabled: dayParams != null,
    placeholderData: (prev) =>
      prev && dayParams && prev.teacher_id === dayParams.teacherId ? prev : undefined,
  })

  const info = key ? remainingByKey.get(key) : undefined
  const visible = Boolean(key)
  const teacherName = info?.teacher_name || teacherDayQ.data?.teacher_name || ''
  const showDayGrid = dayParams != null

  useLayoutEffect(() => {
    const tip = hostRef.current
    const card = tip?.closest('.schedule-grid-card')
    if (!tip || !card || !visible || !slotId) {
      setOverCell(false)
      return
    }

    let raf = 0
    const measure = () => {
      raf = 0
      const cell = hoverCellEl(card, slotId, key)
      if (!cell) {
        setOverCell(false)
        return
      }
      setOverCell(rectsOverlap(tip.getBoundingClientRect(), cell.getBoundingClientRect()))
    }
    const schedule = () => {
      if (raf) return
      raf = window.requestAnimationFrame(measure)
    }

    schedule()
    const viewport = card.querySelector('.overlay-scroll-viewport')
    viewport?.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
    const ro = new ResizeObserver(schedule)
    ro.observe(tip)
    const cell = hoverCellEl(card, slotId, key)
    if (cell) ro.observe(cell)

    return () => {
      if (raf) window.cancelAnimationFrame(raf)
      viewport?.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
      ro.disconnect()
    }
  }, [visible, slotId, key, showDayGrid, teacherDayQ.data, info?.remaining_hours])

  return (
    <div
      ref={hostRef}
      className={`teacher-remaining-tip${visible ? ' is-visible' : ''}${
        info && info.remaining_hours > 0 ? ' is-pending' : ''
      }${overCell ? ' is-over-cell' : ''}`}
      role="status"
      aria-live="polite"
      aria-hidden={!visible}
    >
      {visible ? (
        <>
          {teacherName ? <div className="teacher-remaining-tip-name">{teacherName}</div> : null}
          {showDayGrid ? (
            <TeacherDayGrid
              data={teacherDayQ.data}
              loading={teacherDayQ.isLoading && !teacherDayQ.data}
              error={teacherDayQ.isError ? extractApiError(teacherDayQ.error) : null}
              occupiedOnly
            />
          ) : null}
          {info && info.remaining_hours > 0 ? (
            <>
              <div className="teacher-remaining-tip-total">
                Не распределено: {info.remaining_hours} {lessonsWord(info.remaining_hours)}
              </div>
              <ul className="teacher-remaining-tip-classes">
                {info.classes.map((row) => (
                  <li key={row.class_id}>{classLine(row)}</li>
                ))}
              </ul>
            </>
          ) : (
            <div className="teacher-remaining-tip-total">Все уроки распределены</div>
          )}
        </>
      ) : null}
    </div>
  )
}
