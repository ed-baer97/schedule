/** Mirrors app/domain/classroom_rules.py for grid UI filtering. */

export type ClassroomFact = {
  id: number
  subject_id: number | null
  is_exclusive: boolean
}

export function roomAllowsSubject(
  room: ClassroomFact,
  opts: { subject_id: number; requires_fixed_classroom: boolean },
): boolean {
  if (opts.requires_fixed_classroom) {
    return room.subject_id === opts.subject_id
  }
  if (room.is_exclusive) {
    return room.subject_id === opts.subject_id
  }
  return true
}
