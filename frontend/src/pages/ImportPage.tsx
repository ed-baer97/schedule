import { useState } from 'react'
import { PageHeader } from '../components/PageHeader'

type HoursResult = {
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

type Flash = { kind: 'success' | 'danger'; text: string }

export function ImportPage() {
  const [hoursPending, setHoursPending] = useState(false)
  const [hoursFlash, setHoursFlash] = useState<Flash | null>(null)
  const [hoursWarnings, setHoursWarnings] = useState<string[]>([])
  const [subjectOverride, setSubjectOverride] = useState('')

  async function uploadSubjectHours(fileList: FileList) {
    const files = Array.from(fileList)
    if (files.length === 0) return
    setHoursPending(true)
    setHoursFlash(null)
    setHoursWarnings([])
    try {
      const fd = new FormData()
      for (const file of files) {
        fd.append('files', file)
      }
      const override = subjectOverride.trim()
      if (override) {
        if (files.length > 1) {
          setHoursFlash({
            kind: 'danger',
            text: 'Название предмета можно задать только при загрузке одного файла',
          })
          return
        }
        fd.append('subject', override)
      }
      const res = await fetch('/api/import/subject-hours', {
        method: 'POST',
        body: fd,
        credentials: 'include',
      })
      const text = await res.text()
      let parsed: HoursResult = {}
      try {
        parsed = text ? JSON.parse(text) : {}
      } catch {
        /* leave */
      }
      if (!res.ok) {
        const detail = parsed.detail ?? text ?? `HTTP ${res.status}`
        setHoursFlash({ kind: 'danger', text: String(detail) })
        return
      }
      const warnings = (parsed.files ?? []).flatMap((f) => f.warnings)
      setHoursWarnings(warnings)
      setHoursFlash({
        kind: 'success',
        text: parsed.message ?? 'Импорт завершён',
      })
    } catch (e) {
      setHoursFlash({
        kind: 'danger',
        text: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setHoursPending(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="Импорт данных из Excel"
        subtitle="Два типа файлов: нагрузка по предметам и кабинеты. Шаблон кабинетов будет добавлен отдельно."
      />

      <div className="row g-3">
        <div className="col-lg-7">
          <div className="card shadow-sm h-100">
            <div className="card-header">Нагрузка по предметам</div>
            <div className="card-body">
              <p className="text-muted small mb-2">
                Один Excel-файл на предмет. Можно выбрать сразу несколько файлов.
              </p>
              <ul className="small text-muted">
                <li>Первый столбец — список учителей</li>
                <li>Дальше столбцы — классы (1А, 5Б…)</li>
                <li>В ячейках — часы в неделю (пусто или 0 = не ведёт)</li>
                <li>
                  Два учителя с часами в одном классе → предмет на подгруппы
                </li>
                <li>
                  Один и тот же учитель в нескольких файлах → несколько предметов
                </li>
              </ul>
              <p className="small text-muted">
                Название предмета берётся из имени файла (например{' '}
                <code>Математика.xlsx</code>), либо задайте его ниже для одного
                файла.
              </p>

              <label className="form-label small mb-1" htmlFor="subject-override">
                Предмет (необязательно, только для одного файла)
              </label>
              <input
                id="subject-override"
                className="form-control form-control-sm mb-3"
                value={subjectOverride}
                onChange={(e) => setSubjectOverride(e.target.value)}
                placeholder="Математика"
                disabled={hoursPending}
              />

              <input
                type="file"
                className="form-control mb-2"
                accept=".xlsx,.xls"
                multiple
                onChange={(e) => {
                  const list = e.target.files
                  if (!list?.length) return
                  void uploadSubjectHours(list)
                  e.target.value = ''
                }}
                disabled={hoursPending}
              />

              {hoursPending && <div className="small text-muted">Загрузка…</div>}
              {hoursFlash && (
                <div className={`alert alert-${hoursFlash.kind} py-2 mt-2 mb-0`}>
                  {hoursFlash.text}
                </div>
              )}
              {hoursWarnings.length > 0 && (
                <ul className="small text-warning mt-2 mb-0">
                  {hoursWarnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>

        <div className="col-lg-5">
          <div className="card shadow-sm h-100">
            <div className="card-header">Кабинеты и предметы</div>
            <div className="card-body">
              <p className="text-muted small mb-2">
                Второй файл: кабинеты и предметы, которые в них проводятся.
              </p>
              <p className="small text-muted mb-0">
                Шаблон пока не фиксируем — загрузка откроется, когда придёт
                формат файла.
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="card mt-3">
        <div className="card-header fw-semibold">Как это сохраняется</div>
        <div className="card-body small text-muted">
          <ol className="mb-0">
            <li>Учителя, классы и предмет создаются из файла нагрузки</li>
            <li>
              Каждая ячейка с часами — назначение: учитель + предмет + класс +
              часы
            </li>
            <li>
              Если в одном классе по этому предмету часы у двух учителей —
              ставятся подгруппы
            </li>
            <li>
              Кабинеты пока заводятся вручную или после появления второго шаблона
            </li>
          </ol>
        </div>
      </div>
    </div>
  )
}
