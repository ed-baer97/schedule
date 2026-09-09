import { useEffect, useRef, useState } from 'react'
import type { TeacherRemainingSubject } from '../api/schedule'

export type ClassRemainingSubject = TeacherRemainingSubject & {
  teacher_name: string
}

export type ClassRemaining = {
  class_id: number
  class_name: string
  remaining_hours: number
  subjects: ClassRemainingSubject[]
}

function lessonsWord(n: number) {
  const n10 = n % 10
  const n100 = n % 100
  if (n10 === 1 && n100 !== 11) return 'урок'
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return 'урока'
  return 'уроков'
}

function subjectLine(subject: ClassRemainingSubject) {
  const name =
    subject.group_number != null
      ? `${subject.subject_name} гр.${subject.group_number}`
      : subject.subject_name
  const teacher = subject.teacher_name ? ` (${subject.teacher_name})` : ''
  return `${name} — ${subject.remaining_hours}${teacher}`
}

export function ClassRemainingTip({
  remainingByClassId,
}: {
  remainingByClassId: Map<number, ClassRemaining>
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [classId, setClassId] = useState<number | null>(null)

  useEffect(() => {
    const card = hostRef.current?.closest('.schedule-grid-card')
    if (!card) return

    const sync = () => {
      const raw = card.getAttribute('data-hover-class')
      const n = raw ? Number(raw) : NaN
      setClassId(Number.isFinite(n) ? n : null)
    }
    sync()
    const obs = new MutationObserver(sync)
    obs.observe(card, {
      attributes: true,
      attributeFilter: ['data-hover-class'],
    })
    return () => obs.disconnect()
  }, [])

  const info = classId != null ? remainingByClassId.get(classId) : undefined
  const visible = classId != null
  const pending = Boolean(info && info.remaining_hours > 0)

  return (
    <div
      ref={hostRef}
      className={`class-remaining-tip${visible ? ' is-visible' : ''}${
        pending ? ' is-pending' : ''
      }`}
      role="status"
      aria-live="polite"
      aria-hidden={!visible}
    >
      {visible ? (
        <>
          <div className="class-remaining-tip-name">{info?.class_name ?? `Класс ${classId}`}</div>
          {pending && info ? (
            <>
              <div className="class-remaining-tip-total">
                Не распределено: {info.remaining_hours} {lessonsWord(info.remaining_hours)}
              </div>
              <ul className="class-remaining-tip-subjects">
                {info.subjects.map((row, i) => (
                  <li key={`${row.subject_name}-${row.group_number ?? 0}-${row.teacher_name}-${i}`}>
                    {subjectLine(row)}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <div className="class-remaining-tip-total">Все уроки распределены</div>
          )}
        </>
      ) : null}
    </div>
  )
}
