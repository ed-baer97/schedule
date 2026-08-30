/** Mirrors app/domain/classroom_rules.py for grid UI filtering. */

export type ClassroomFact = {
  id: number
  subject_ids: number[]
  is_exclusive: boolean
  school_level?: string | null
}

export function roomHasSubject(room: ClassroomFact, subjectId: number): boolean {
  return room.subject_ids.includes(subjectId)
}

export function roomAllowsSubject(
  room: ClassroomFact,
  opts: { subject_id: number; requires_fixed_classroom: boolean },
): boolean {
  if (opts.requires_fixed_classroom) {
    return roomHasSubject(room, opts.subject_id)
  }
  if (room.is_exclusive) {
    return roomHasSubject(room, opts.subject_id)
  }
  return true
}

export function roomAllowsLevel(
  room: ClassroomFact,
  classSchoolLevel?: string | null,
): boolean {
  const tagged = room.school_level ?? null
  if (!tagged) return true
  if (!classSchoolLevel) return true
  return tagged === classSchoolLevel
}

export function roomAllows(
  room: ClassroomFact,
  opts: {
    subject_id: number
    requires_fixed_classroom: boolean
    class_school_level?: string | null
  },
): boolean {
  if (!roomAllowsLevel(room, opts.class_school_level ?? null)) return false
  return roomAllowsSubject(room, opts)
}

type OccupyingCell = {
  classroom_id: number | null
  day_of_week: number
  lesson_number: number
}

/** True if another class can still take this room at the slot (mirrors classroom_at_capacity). */
export function roomFreeAtSlot(
  room: { id: number; classes_capacity?: number | null },
  cells: OccupyingCell[],
  slot: { day: number; lesson: number },
): boolean {
  const cap = Math.max(1, room.classes_capacity ?? 1)
  let occupying = 0
  for (const cell of cells) {
    if (
      cell.classroom_id === room.id &&
      cell.day_of_week === slot.day &&
      cell.lesson_number === slot.lesson
    ) {
      occupying += 1
      if (occupying >= cap) return false
    }
  }
  return true
}
