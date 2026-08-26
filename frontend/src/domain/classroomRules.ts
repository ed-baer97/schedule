/** Mirrors app/domain/classroom_rules.py for grid UI filtering. */

export type ClassroomFact = {
  id: number
  subject_ids: number[]
  is_exclusive: boolean
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
