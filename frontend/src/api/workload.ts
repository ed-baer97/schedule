import { apiJson } from './client'
import type { SchoolLevel } from '../domain/schoolLevel'

export type WorkloadClassBrief = { id: number; name: string; grade: number }
export type WorkloadSubjectBrief = { id: number; name: string }
export type WorkloadCell = { class_id: number; subject_id: number; hours: number }

export type WorkloadData = {
  school_level: string
  classes: WorkloadClassBrief[]
  subjects: WorkloadSubjectBrief[]
  cells: WorkloadCell[]
}

export function fetchWorkload(schoolLevel: SchoolLevel) {
  return apiJson<WorkloadData>(`/api/workload/?school_level=${schoolLevel}`)
}

export function updateWorkloadCell(payload: WorkloadCell) {
  return apiJson<void>('/api/workload/cell', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}
