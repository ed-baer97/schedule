/** Mirrors app/domain/schedule_rules.py groups_can_share_slot. */
export function groupsCanShareSlot(
  groupA: number | null,
  groupB: number | null,
  subjectIdA?: number | null,
  subjectIdB?: number | null,
): boolean {
  if (groupA == null || groupB == null) return false
  if (groupA === groupB) return false
  if (subjectIdA != null && subjectIdB != null && subjectIdA !== subjectIdB) return false
  return true
}

type OccupiedCell = {
  assignment_id: number
  group_number: number | null
  subject_id: number
}

type CandidateAssignment = {
  id: number
  group_number: number | null
  subject_id: number
}

/** Empty slot: any remaining assignment. Occupied: only a complementary subgroup. */
export function assignmentCanJoinSlot(
  assignment: CandidateAssignment,
  occupied: OccupiedCell[],
): boolean {
  if (occupied.length === 0) return true
  return occupied.every(
    (cell) =>
      cell.assignment_id !== assignment.id &&
      groupsCanShareSlot(
        assignment.group_number,
        cell.group_number,
        assignment.subject_id,
        cell.subject_id,
      ),
  )
}

/** Whole-class lessons fill the slot; subgroup cards can share it. */
export function slotAcceptsAnotherLesson(cells: { group_number: number | null }[]): boolean {
  if (cells.length === 0) return true
  return cells.every((c) => c.group_number != null)
}
