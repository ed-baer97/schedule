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
