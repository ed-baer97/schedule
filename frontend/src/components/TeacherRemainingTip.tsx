import { useEffect, useRef, useState } from 'react'
import type { TeacherRemaining, TeacherRemainingClass } from '../api/schedule'

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

export function TeacherRemainingTip({
  remainingByKey,
}: {
  remainingByKey: Map<string, TeacherRemaining>
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [key, setKey] = useState<string | null>(null)

  useEffect(() => {
    const card = hostRef.current?.closest('.schedule-grid-card')
    if (!card) return

    const sync = () => setKey(card.getAttribute('data-hover-teacher'))
    sync()
    const obs = new MutationObserver(sync)
    obs.observe(card, { attributes: true, attributeFilter: ['data-hover-teacher'] })
    return () => obs.disconnect()
  }, [])

  const info = key ? remainingByKey.get(key) : undefined
  const visible = Boolean(key)

  return (
    <div
      ref={hostRef}
      className={`teacher-remaining-tip${visible ? ' is-visible' : ''}${
        info && info.remaining_hours > 0 ? ' is-pending' : ''
      }`}
      role="status"
      aria-live="polite"
      aria-hidden={!visible}
    >
      {visible && info ? (
        <>
          <div className="teacher-remaining-tip-name">{info.teacher_name}</div>
          {info.remaining_hours > 0 ? (
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
      ) : visible ? (
        <div className="teacher-remaining-tip-total">Все уроки распределены</div>
      ) : null}
    </div>
  )
}
