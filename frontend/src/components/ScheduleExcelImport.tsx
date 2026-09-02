import { useId, useState } from 'react'
import { uploadScheduleExcel } from '../api/import'

type Flash = { kind: 'success' | 'danger'; text: string }

export function ScheduleExcelImport({ compact = false }: { compact?: boolean }) {
  const replaceId = useId()
  const [pending, setPending] = useState(false)
  const [replace, setReplace] = useState(true)
  const [flash, setFlash] = useState<Flash | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])

  async function onFile(fileList: FileList | null) {
    const file = fileList?.[0]
    if (!file) return
    setPending(true)
    setFlash(null)
    setWarnings([])
    try {
      const result = await uploadScheduleExcel(file, replace)
      setWarnings(result.warnings ?? [])
      setFlash({
        kind: result.placed > 0 ? 'success' : 'danger',
        text: result.message || 'Импорт завершён',
      })
    } catch (err) {
      setFlash({
        kind: 'danger',
        text: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setPending(false)
    }
  }

  return (
    <div>
      {!compact && (
        <p className="text-muted small mb-2">
          Файл из «Отчёты» — полное расписание школы, класс или учитель. Сетка
          восстанавливается по уже существующим назначениям (предмет, учитель,
          класс, кабинет).
        </p>
      )}
      <div className="form-check mb-2">
        <input
          id={replaceId}
          className="form-check-input"
          type="checkbox"
          checked={replace}
          disabled={pending}
          onChange={(e) => setReplace(e.target.checked)}
        />
        <label className="form-check-label small" htmlFor={replaceId}>
          Очистить уроки классов из файла перед загрузкой
        </label>
      </div>
      <input
        type="file"
        className="form-control"
        accept=".xlsx,.xls"
        disabled={pending}
        onChange={(e) => {
          void onFile(e.target.files)
          e.target.value = ''
        }}
      />
      {pending && <div className="small text-muted mt-2">Загрузка…</div>}
      {flash && (
        <div className={`alert alert-${flash.kind} py-2 mt-2 mb-0`}>{flash.text}</div>
      )}
      {warnings.length > 0 && (
        <ul className="small text-warning mt-2 mb-0">
          {warnings.slice(0, 20).map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
          {warnings.length > 20 && <li>…и ещё {warnings.length - 20}</li>}
        </ul>
      )}
    </div>
  )
}
