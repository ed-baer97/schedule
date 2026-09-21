export type ScheduleKind = 'main' | 'temporary' | 'monthly'

export const MONTHLY_WEEKS = [1, 2, 3, 4] as const
export type MonthlyWeek = (typeof MONTHLY_WEEKS)[number]

export const SCHEDULE_KIND_LABELS: Record<ScheduleKind, string> = {
  main: 'Основное',
  temporary: 'Временное',
  monthly: 'Месячное',
}

export function parseScheduleKind(raw: string | null | undefined): ScheduleKind {
  if (raw === 'temporary' || raw === 'monthly') return raw
  return 'main'
}

export function parseWeekIndex(kind: ScheduleKind, raw: string | null | undefined): number {
  if (kind !== 'monthly') return 0
  const n = Number(raw)
  if (n === 1 || n === 2 || n === 3 || n === 4) return n
  return 1
}

export function cellHourWeight(hoursPerWeek: number | null | undefined): number {
  const h = hoursPerWeek ?? 1
  return h > 0 && h < 1 ? 0.25 : 1
}
