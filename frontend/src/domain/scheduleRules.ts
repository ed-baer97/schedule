/** Mirrors app/domain/schedule_rules.py second_hour_is_split. */
export function secondHourIsSplit(existingLessons: number[], newLesson: number): boolean {
  const existing = [...new Set(existingLessons.map((n) => n))]
  if (existing.length !== 1) return false
  return Math.abs(newLesson - existing[0]) !== 1
}
export function groupsCanShareSlot(
  groupA: number | null,
  groupB: number | null,
  subjectIdA?: number | null,
  subjectIdB?: number | null,
  opts?: { requiresSubgroupA?: boolean; requiresSubgroupB?: boolean },
): boolean {
  if (groupA == null || groupB == null) return false
  const sameSubject =
    subjectIdA != null && subjectIdB != null && subjectIdA === subjectIdB
  if (sameSubject) return groupA !== groupB
  return Boolean(opts?.requiresSubgroupA && opts?.requiresSubgroupB)
}

type OccupiedCell = {
  assignment_id: number
  group_number: number | null
  subject_id: number
  requires_subgroup?: boolean
}

type CandidateAssignment = {
  id: number
  group_number: number | null
  subject_id: number
  requires_subgroup?: boolean
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
        {
          requiresSubgroupA: Boolean(assignment.requires_subgroup),
          requiresSubgroupB: Boolean(cell.requires_subgroup),
        },
      ),
  )
}

/** Whole-class lessons fill the slot; subgroup cards can share it. */
export function slotAcceptsAnotherLesson(cells: { group_number: number | null }[]): boolean {
  if (cells.length === 0) return true
  return cells.every((c) => c.group_number != null)
}
