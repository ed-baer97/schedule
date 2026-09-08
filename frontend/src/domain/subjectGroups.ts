export type SubjectGroup = 'natural_math' | 'humanities' | 'languages' | 'practical'

export const SUBJECT_GROUP_OPTIONS: {
  value: SubjectGroup
  label: string
  hint: string
  badgeClass: string
}[] = [
  {
    value: 'natural_math',
    label: 'Естественно-математический',
    hint: 'математика, физика, химия, биология, информатика',
    badgeClass: 'bg-danger-subtle text-danger-emphasis border border-danger-subtle',
  },
  {
    value: 'humanities',
    label: 'Гуманитарный',
    hint: 'история, география, обществознание, право',
    badgeClass: 'bg-primary-subtle text-primary-emphasis border border-primary-subtle',
  },
  {
    value: 'languages',
    label: 'Языки',
    hint: 'казахский, русский, английский, литература',
    badgeClass: 'bg-info-subtle text-info-emphasis border border-info-subtle',
  },
  {
    value: 'practical',
    label: 'Практические',
    hint: 'физкультура, технология, НВП, ОБЖ и подобные',
    badgeClass: 'bg-success-subtle text-success-emphasis border border-success-subtle',
  },
]

export const SUBJECT_GROUP_LABELS: Record<
  SubjectGroup,
  { label: string; badgeClass: string }
> = Object.fromEntries(
  SUBJECT_GROUP_OPTIONS.map((o) => [o.value, { label: o.label, badgeClass: o.badgeClass }]),
) as Record<SubjectGroup, { label: string; badgeClass: string }>
