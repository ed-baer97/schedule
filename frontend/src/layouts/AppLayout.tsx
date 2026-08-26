import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { fetchHealth } from '../api/health'
import { cancelJob, fetchActiveJob } from '../api/schedule'
import { useAuth } from '../auth/AuthContext'
import { AtmosphereBg } from '../components/AtmosphereBg'
import { BrandMark } from '../components/BrandMark'
import { ThemeToggle } from '../components/ThemeToggle'

function ApiHealthBanner() {
  const q = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
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
        <code>alembic upgrade head</code>
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

function ActiveJobBanner() {
  const loc = useLocation()
  const qc = useQueryClient()
  const prevId = useRef<number | null>(null)
  const [stopping, setStopping] = useState(false)
  const q = useQuery({
    queryKey: ['jobs', 'active'],
    queryFn: fetchActiveJob,
    refetchInterval: (query) => (query.state.data ? 2000 : false),
    retry: false,
  })
  const job = q.data ?? null

  useEffect(() => {
    const id = job?.id ?? null
    if (prevId.current != null && id == null) {
      void qc.invalidateQueries({ queryKey: ['schedule'] })
    }
    prevId.current = id
  }, [job?.id, qc])

  if (!job) return null
  if (loc.pathname.startsWith('/schedule/auto')) return null

  const msg = job.progress?.message
  return (
    <div className="app-health-banner alert alert-info rounded-0 mb-0 py-2 px-3 d-flex justify-content-between align-items-center flex-wrap gap-2">
      <span>
        <strong>Автосоставление выполняется</strong>
        {' '}
        (задача #{job.id}
        {job.status === 'cancelling' ? ', останавливается' : ''}).
        Процесс идёт на сервере
        {msg ? `: ${msg}` : ''}.
      </span>
      <span className="d-flex gap-2">
        <Link className="btn btn-sm btn-outline-dark" to="/schedule/auto">
          Открыть прогресс
        </Link>
        <button
          type="button"
          className="btn btn-sm btn-outline-danger"
          disabled={stopping}
          onClick={() => {
            setStopping(true)
            void cancelJob(job.id)
              .then(() => qc.invalidateQueries({ queryKey: ['jobs'] }))
              .finally(() => setStopping(false))
          }}
        >
          Остановить
        </button>
      </span>
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
  { type: 'link' as const, to: '/teacher-load', icon: 'bi-person-lines-fill', label: 'Нагрузка учителей' },
  { type: 'section' as const, label: 'Расписание' },
  { type: 'link' as const, to: '/schedule', icon: 'bi-calendar3', label: 'Сетка и настройки' },
  { type: 'section' as const, label: 'Данные' },
  { type: 'link' as const, to: '/import', icon: 'bi-file-earmark-excel', label: 'Импорт Excel' },
  { type: 'link' as const, to: '/reports', icon: 'bi-printer', label: 'Отчёты' },
]

function UserMenu() {
  const { user, logout } = useAuth()
  if (!user) return null
  return (
    <div className="d-flex align-items-center gap-2 text-white-50 small">
      <ThemeToggle />
      {user.role === 'platform_admin' ? (
        <Link className="btn btn-sm btn-outline-light" to="/admin">
          Админка
        </Link>
      ) : null}
      <span className="d-none d-md-inline">{user.email}</span>
      <button type="button" className="btn btn-sm btn-outline-light" onClick={() => void logout()}>
        Выйти
      </button>
    </div>
  )
}

export function AppLayout() {
  return (
    <div className="app-shell">
      <AtmosphereBg className="app-atmosphere" />
      <div className="app-glass" aria-hidden />
      <nav className="navbar navbar-dark app-navbar">
        <div className="container-fluid px-3">
          <Link className="navbar-brand text-white d-flex align-items-center gap-2" to="/">
            <BrandMark size={32} />
            KiVi
          </Link>
          <UserMenu />
        </div>
      </nav>
      <ApiHealthBanner />
      <ActiveJobBanner />
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
          <div className="app-main-scroll">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
