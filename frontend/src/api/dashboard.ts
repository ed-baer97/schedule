import { apiJson } from './client'

export type DashboardStats = {
  teachers_count: number
  classes_count: number
  subjects_count: number
  classrooms_count: number
  elementary_classes: number
  secondary_classes: number
  elementary_assignments: number
  secondary_assignments: number
  elementary_scheduled: number
  secondary_scheduled: number
}

export function fetchDashboardStats() {
  return apiJson<DashboardStats>('/api/dashboard/stats')
}
