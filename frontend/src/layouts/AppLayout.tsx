import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { apiJson } from '../api/client'

type HealthResponse = {
  status: string
  database: {
    connected: boolean
    schema_ready: boolean
    missing_tables?: string[]
    missing_columns?: Record<string, string[]>
    message?: string
    error?: string
  }
}

function ApiHealthBanner() {
  const q = useQuery({
    queryKey: ['health'],
    queryFn: () => apiJson<HealthResponse>('/api/health'),
    refetchInterval: 8000,
    refetchIntervalInBackground: true,
    retry: false,
    staleTime: 0,
  })

  if (q.isLoading) return null
  if (!q.isError && q.data?.status === 'ok') return null

  const db = q.data?.database
  const schemaIssue = db && db.connected && !db.schema_ready
  const offline = q.isError || (db && !db.connected)

  let message: ReactNode
  if (offline) {
    message = (
      <>
        <strong>API недоступен.</strong> Запустите backend: <code>python run_api.py</code> или{' '}
        <code>npm run dev</code> из корня проекта.
      </>
    )
  } else if (schemaIssue) {
    message = (
      <>
        <strong>База данных не готова.</strong> Выполните из корня:{' '}
        <code>set FLASK_APP=run.py</code> и <code>flask db upgrade</code>
        {db.missing_tables?.length ? (
          <span className="d-block small mt-1 opacity-75">
            Нет таблиц: {db.missing_tables.join(', ')}
          </span>
        ) : null}
        {db.missing_columns && Object.keys(db.missing_columns).length > 0 ? (
          <span className="d-block small mt-1 opacity-75">
            Нет колонок:{' '}
            {Object.entries(db.missing_columns)
              .map(([table, cols]) => `${table} (${cols.join(', ')})`)
              .join('; ')}
          </span>
        ) : null}
      </>
    )
  } else {
    message = <strong>Сервис в деградированном режиме.</strong>
  }

  return (
    <div
      className={`app-health-banner alert ${offline || schemaIssue ? 'alert-danger' : 'alert-warning'} rounded-0 mb-0 py-2 px-3 d-flex justify-content-between align-items-center flex-wrap gap-2`}
    >
      <span>{message}</span>
      <button type="button" className="btn btn-sm btn-outline-dark" onClick={() => q.refetch()}>
        Повторить
      </button>
    </div>
  )
}

const NAV = [
  { type: 'link' as const, to: '/', icon: 'bi-house', label: 'Главная' },
  { type: 'section' as const, label: 'Справочники' },
  { type: 'link' as const, to: '/teachers', icon: 'bi-people', label: 'Учителя' },
  { type: 'link' as const, to: '/classrooms', icon: 'bi-door-open', label: 'Кабинеты' },
  { type: 'link' as const, to: '/school-classes', icon: 'bi-mortarboard', label: 'Классы' },
  { type: 'link' as const, to: '/shifts', icon: 'bi-clock', label: 'Смены' },
  { type: 'link' as const, to: '/subjects', icon: 'bi-journal-text', label: 'Предметы' },
  { type: 'section' as const, label: 'Нагрузка' },
  { type: 'link' as const, to: '/workload', icon: 'bi-table', label: 'Часы' },
  { type: 'link' as const, to: '/assignments', icon: 'bi-person-check', label: 'Назначения' },
  { type: 'section' as const, label: 'Расписание' },
  { type: 'link' as const, to: '/schedule', icon: 'bi-calendar3', label: 'Сетка и настройки' },
  { type: 'section' as const, label: 'Данные' },
  { type: 'link' as const, to: '/import', icon: 'bi-file-earmark-excel', label: 'Импорт Excel' },
  { type: 'link' as const, to: '/reports', icon: 'bi-printer', label: 'Отчёты' },
]

export function AppLayout() {
  return (
    <div className="app-shell">
      <nav className="navbar navbar-dark app-navbar">
        <div className="container-fluid px-3">
          <Link className="navbar-brand text-white" to="/">
            <i className="bi bi-calendar-week me-2" />
            Школьное расписание
          </Link>
        </div>
      </nav>
      <ApiHealthBanner />
      <div className="app-body">
        <aside className="app-sidebar">
          <nav className="nav flex-column sidebar-nav">
            {NAV.map((item, i) =>
              item.type === 'section' ? (
                <div key={`s-${i}`} className="nav-section">
                  {item.label}
                </div>
              ) : (
                <NavLink key={item.to} className="nav-link" to={item.to} end={item.to === '/'}>
                  <i className={`bi ${item.icon}`} />
                  {item.label}
                </NavLink>
              ),
            )}
          </nav>
        </aside>
        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
