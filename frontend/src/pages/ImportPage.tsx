import { useState } from 'react'
import { PageHeader } from '../components/PageHeader'

import { uploadSubjectHours as importSubjectHours } from '../api/import'
import { ScheduleExcelImport } from '../components/ScheduleExcelImport'

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
      const override = subjectOverride.trim()
      if (override) {
        if (files.length > 1) {
          setHoursFlash({
            kind: 'danger',
            text: 'Название предмета можно задать только при загрузке одного файла',
          })
          return
        }
      }
      const parsed = await importSubjectHours(files, override || undefined)
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
                Один файл на предмет или одна книга с несколькими листами
                (как «Скачать Excel» на странице нагрузки учителей). Можно
                выбрать сразу несколько файлов.
              </p>
              <ul className="small text-muted">
                <li>
                  Строка заголовков: <code>№</code>, <code>ФИО</code>, классы
                  (1А, 5Б…), при необходимости <code>итого</code>
                </li>
                <li>
                  В книге с несколькими листами каждый лист — отдельный предмет
                  (имя листа или строка над таблицей)
                </li>
                <li>
                  Над таблицей можно указать предмет (как в ячейке B1) и учебный
                  год — год не импортируется
                </li>
                <li>В ячейках — часы в неделю (пусто или 0 = не ведёт)</li>
                <li>
                  Два учителя с часами в одном классе → предмет на подгруппы
                </li>
                <li>
                  Одно и то же ФИО на разных листах/в файлах — один учитель,
                  несколько предметов. Не дублируется
                </li>
              </ul>
              <p className="small text-muted">
                Название предмета: ячейка в шапке или имя листа; для файла с
                одним листом — ещё имя файла (<code>Инф.xlsx</code>). Ниже
                можно задать вручную только для одного листа/файла.
              </p>

              <label className="form-label small mb-1" htmlFor="subject-override">
                Предмет (необязательно, только для одного файла с одним листом)
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
        <div className="card-header">Вернуть сетку из Excel</div>
        <div className="card-body">
          <ScheduleExcelImport />
        </div>
      </div>

      <div className="card mt-3">
        <div className="card-header fw-semibold">Как это сохраняется</div>
        <div className="card-body small text-muted">
          <ol className="mb-0">
            <li>
              Учителя, классы и предмет создаются из файла нагрузки. Один
              файл может содержать несколько листов (предмет на лист). Повтор
              того же ФИО в другом предмете присоединяется к уже созданному
              учителю
            </li>
            <li>
              Каждая ячейка с часами — назначение: учитель + предмет + класс +
              часы. Столбец «итого» и номера строк не загружаются
            </li>
            <li>
              Если в одном классе по этому предмету часы у двух учителей —
              ставятся подгруппы
            </li>
            <li>
              Кабинеты пока заводятся вручную или после появления второго шаблона
            </li>
            <li>
              Сетка из Excel-отчёта не создаёт справочники — только уроки по уже
              существующим назначениям
            </li>
          </ol>
        </div>
      </div>
    </div>
  )
}
