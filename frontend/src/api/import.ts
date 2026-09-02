export type SubjectHoursImportResult = {
  message?: string
  detail?: string
  files?: Array<{
    subject: string
    teachers_created: number
    classes_created: number
    assignments_created: number
    assignments_updated: number
    subgroup_classes: number
    warnings: string[]
  }>
}

export type ScheduleImportResult = {
  placed: number
  skipped_existing: number
  unmatched: number
  cleared: number
  warnings: string[]
  message: string
  detail?: string
}

export async function uploadSubjectHours(files: File[], subjectOverride?: string) {
  const fd = new FormData()
  for (const file of files) {
    fd.append('files', file)
  }
  if (subjectOverride?.trim()) {
    fd.append('subject', subjectOverride.trim())
  }
  const res = await fetch('/api/import/subject-hours', {
    method: 'POST',
    body: fd,
    credentials: 'include',
  })
  const text = await res.text()
  let parsed: SubjectHoursImportResult = {}
  try {
    parsed = text ? JSON.parse(text) : {}
  } catch {
    /* leave */
  }
  if (!res.ok) {
    const detail = parsed.detail ?? text ?? `HTTP ${res.status}`
    throw new Error(String(detail))
  }
  return parsed
}

export async function uploadScheduleExcel(file: File, replace: boolean) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('replace', replace ? 'true' : 'false')
  const res = await fetch('/api/import/schedule', {
    method: 'POST',
    body: fd,
    credentials: 'include',
  })
  const text = await res.text()
  let parsed: ScheduleImportResult = {
    placed: 0,
    skipped_existing: 0,
    unmatched: 0,
    cleared: 0,
    warnings: [],
    message: '',
  }
  try {
    parsed = text ? { ...parsed, ...JSON.parse(text) } : parsed
  } catch {
    /* leave */
  }
  if (!res.ok) {
    const detail = parsed.detail ?? text ?? `HTTP ${res.status}`
    throw new Error(String(detail))
  }
  return parsed
}
