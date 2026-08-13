import { useState } from 'react'

type ImportKind = 'teachers' | 'classrooms' | 'curriculum_elementary' | 'curriculum_secondary'

type CardConfig = {
  kind: ImportKind
  title: string
  description: string
  bullets: string[]
  uploadPath: string
  templatePath: string
  headerClass: string
  buttonClass: string
}

const CARDS: CardConfig[] = [
  {
    kind: 'teachers',
    title: 'Список учителей',
    description: 'Excel файл с колонками:',
    bullets: ['ФИО — полное имя (обязательно)', 'Краткое имя', 'Email', 'Телефон'],
    uploadPath: '/api/import/teachers',
    templatePath: '/api/import/template/teachers',
    headerClass: 'bg-primary text-white',
    buttonClass: 'btn btn-primary',
  },
  {
    kind: 'classrooms',
    title: 'Кабинеты',
    description: 'Excel файл с колонками:',
    bullets: [
      'Номер — номер кабинета (обязательно)',
      'Название — тип кабинета',
      'Вместимость классов',
      'Этаж, Корпус',
    ],
    uploadPath: '/api/import/classrooms',
    templatePath: '/api/import/template/classrooms',
    headerClass: 'bg-info text-white',
    buttonClass: 'btn btn-info text-white',
  },
  {
    kind: 'curriculum_elementary',
    title: 'Учебный план: Начальная школа',
    description: 'Таблица часов: строки — классы, столбцы — предметы, ячейки — часы в неделю.',
    bullets: [
      'Строки — классы (1А, 1Б…)',
      'Столбцы — предметы',
      'Ячейки — часы в неделю (0 = не преподаётся)',
    ],
    uploadPath: '/api/import/curriculum/elementary',
    templatePath: '/api/import/template/curriculum_elementary',
    headerClass: 'bg-success text-white',
    buttonClass: 'btn btn-success',
  },
  {
    kind: 'curriculum_secondary',
    title: 'Учебный план: Основная школа',
    description: 'Таблица часов: строки — классы, столбцы — предметы, ячейки — часы в неделю.',
    bullets: [
      'Строки — классы (5А, 6Б, 11В…)',
      'Столбцы — предметы',
      'Ячейки — часы в неделю (0 = не преподаётся)',
    ],
    uploadPath: '/api/import/curriculum/secondary',
    templatePath: '/api/import/template/curriculum_secondary',
    headerClass: 'text-white',
    buttonClass: 'btn text-white',
  },
]

type UploadResult = { kind: 'success' | 'danger'; text: string }

export function ImportPage() {
  const [results, setResults] = useState<Record<ImportKind, UploadResult | null>>({
    teachers: null,
    classrooms: null,
    curriculum_elementary: null,
    curriculum_secondary: null,
  })
  const [pending, setPending] = useState<Record<ImportKind, boolean>>({
    teachers: false,
    classrooms: false,
    curriculum_elementary: false,
    curriculum_secondary: false,
  })

  async function handleUpload(kind: ImportKind, path: string, file: File) {
    setPending((p) => ({ ...p, [kind]: true }))
    setResults((r) => ({ ...r, [kind]: null }))
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch(path, { method: 'POST', body: fd })
      const text = await res.text()
      let parsed: { message?: string; detail?: string } = {}
      try {
        parsed = text ? JSON.parse(text) : {}
      } catch {
        /* leave as text */
      }
      if (!res.ok) {
        const detail = parsed.detail ?? text ?? `HTTP ${res.status}`
        setResults((r) => ({ ...r, [kind]: { kind: 'danger', text: String(detail) } }))
      } else {
        setResults((r) => ({
          ...r,
          [kind]: { kind: 'success', text: parsed.message ?? 'Импорт завершён' },
        }))
      }
    } catch (e) {
      setResults((r) => ({
        ...r,
        [kind]: { kind: 'danger', text: e instanceof Error ? e.message : String(e) },
      }))
    } finally {
      setPending((p) => ({ ...p, [kind]: false }))
    }
  }

  return (
    <div>
      <h1 className="h3 mb-3">Импорт данных из Excel</h1>
      <div className="row g-3">
        {CARDS.map((c) => (
          <div className="col-md-6" key={c.kind}>
            <div className="card shadow-sm h-100">
              <div
                className={`card-header ${c.headerClass}`}
                style={c.kind === 'curriculum_secondary' ? { background: '#9b59b6' } : undefined}
              >
                {c.title}
              </div>
              <div className="card-body">
                <p className="text-muted small mb-1">{c.description}</p>
                <ul className="small text-muted">
                  {c.bullets.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>

                <a
                  href={c.templatePath}
                  className="btn btn-outline-secondary btn-sm mb-3"
                >
                  Скачать шаблон
                </a>

                <input
                  type="file"
                  className="form-control mb-2"
                  accept=".xlsx,.xls"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (!file) return
                    handleUpload(c.kind, c.uploadPath, file)
                    e.target.value = ''
                  }}
                  disabled={pending[c.kind]}
                />

                {pending[c.kind] && (
                  <div className="small text-muted">Загрузка…</div>
                )}
                {results[c.kind] && (
                  <div className={`alert alert-${results[c.kind]!.kind} py-2 mt-2 mb-0`}>
                    {results[c.kind]!.text}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="card mt-3">
        <div className="card-header fw-semibold">Порядок импорта</div>
        <div className="card-body small text-muted">
          <ol className="mb-0">
            <li>Список учителей</li>
            <li>Кабинеты</li>
            <li>Учебный план начальной школы</li>
            <li>Учебный план основной школы</li>
            <li>В разделе «Назначения» распределите учителей по предметам</li>
          </ol>
        </div>
      </div>
    </div>
  )
}
