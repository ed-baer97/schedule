/** Weekday labels shared across UI (1=Mon … 6=Sat). */
export const DAY_NAMES_LIST = [
  'Понедельник',
  'Вторник',
  'Среда',
  'Четверг',
  'Пятница',
  'Суббота',
] as const

export const DAY_NAMES: Record<number, string> = Object.fromEntries(
  DAY_NAMES_LIST.map((name, i) => [i + 1, name]),
) as Record<number, string>
