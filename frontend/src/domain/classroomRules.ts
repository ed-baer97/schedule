/** Mirrors app/domain/classroom_rules.py for grid UI filtering. */

export type ClassroomFact = {
  id: number
  subject_ids: number[]
  is_exclusive: boolean
  school_level?: string | null
  subgroup_only?: boolean
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

export function roomAllowsSubgroup(room: ClassroomFact, isSubgroup: boolean): boolean {
  if (!room.subgroup_only) return true
  return Boolean(isSubgroup)
}

export function roomAllows(
  room: ClassroomFact,
  opts: {
    subject_id: number
    requires_fixed_classroom: boolean
    class_school_level?: string | null
    is_subgroup?: boolean
  },
): boolean {
  if (!roomAllowsLevel(room, opts.class_school_level ?? null)) return false
  if (!roomAllowsSubgroup(room, Boolean(opts.is_subgroup))) return false
  return roomAllowsSubject(room, opts)
}

type OccupyingCell = {
  id?: number
  classroom_id: number | null
  day_of_week: number
  lesson_number: number
}

function occupiesSlot(
  cell: OccupyingCell,
  slot: { day: number; lesson: number },
  classroomId: number,
  excludeCellId?: number | null,
): boolean {
  if (excludeCellId != null && cell.id === excludeCellId) return false
  return (
    cell.classroom_id === classroomId &&
    cell.day_of_week === slot.day &&
    cell.lesson_number === slot.lesson
  )
}

/** True if another class can still take this room at the slot (mirrors classroom_at_capacity). */
export function roomFreeAtSlot(
  room: { id: number; classes_capacity?: number | null },
  cells: OccupyingCell[],
  slot: { day: number; lesson: number },
  excludeCellId?: number | null,
): boolean {
  const cap = Math.max(1, room.classes_capacity ?? 1)
  let occupying = 0
  for (const cell of cells) {
    if (occupiesSlot(cell, slot, room.id, excludeCellId)) {
      occupying += 1
      if (occupying >= cap) return false
    }
  }
  return true
}

export function occupantsAtSlot<T extends OccupyingCell>(
  cells: T[],
  slot: { day: number; lesson: number },
  classroomId: number,
  excludeCellId?: number | null,
): T[] {
  return cells.filter((cell) => occupiesSlot(cell, slot, classroomId, excludeCellId))
}
