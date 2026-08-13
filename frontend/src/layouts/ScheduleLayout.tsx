import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { PageHeader } from '../components/PageHeader'

type ExpandCtx = {
  expanded: boolean
  setExpanded: Dispatch<SetStateAction<boolean>>
}

const ScheduleExpandContext = createContext<ExpandCtx | null>(null)

export function useScheduleExpand() {
  const ctx = useContext(ScheduleExpandContext)
  if (!ctx) throw new Error('useScheduleExpand must be used inside ScheduleLayout')
  return ctx
}

function loadExpanded(): boolean {
  try {
    return sessionStorage.getItem('schedule:expanded') === '1'
  } catch {
    return false
  }
}

export function ScheduleLayout() {
  const loc = useLocation()
  const isGrid = loc.pathname === '/schedule' || loc.pathname === '/schedule/'
  const [expanded, setExpanded] = useState(loadExpanded)

  useEffect(() => {
    try {
      sessionStorage.setItem('schedule:expanded', expanded ? '1' : '0')
    } catch {
      /* ignore */
    }
    document.body.classList.toggle('schedule-grid-expanded', expanded)
    return () => document.body.classList.remove('schedule-grid-expanded')
  }, [expanded])

  useEffect(() => {
    if (!expanded) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpanded(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [expanded])

  const value = useMemo(() => ({ expanded, setExpanded }), [expanded])

  return (
    <ScheduleExpandContext.Provider value={value}>
      <div className="schedule-hub">
        <PageHeader
          title="Расписание"
          subtitle="Сетка уроков и автозаполнение"
          actions={
            isGrid ? (
              <button
                type="button"
                className={`btn btn-sm schedule-expand-btn ${expanded ? 'btn-dark' : 'btn-outline-secondary'}`}
                title={expanded ? 'Свернуть таблицу' : 'Растянуть таблицу на весь экран'}
                aria-pressed={expanded}
                aria-label={expanded ? 'Свернуть таблицу' : 'Растянуть таблицу на весь экран'}
                onClick={() => setExpanded((v) => !v)}
              >
                <i className={`bi ${expanded ? 'bi-arrows-angle-contract' : 'bi-arrows-fullscreen'}`} />
                <span className="ms-1">{expanded ? 'Свернуть' : 'На весь экран'}</span>
              </button>
            ) : null
          }
        />
        <ul className="nav nav-tabs schedule-hub-tabs mb-4">
          <li className="nav-item">
            <NavLink className="nav-link" to="/schedule" end>
              <i className="bi bi-grid-3x3-gap me-1" />
              Сетка
            </NavLink>
          </li>
          <li className="nav-item">
            <NavLink className="nav-link" to="/schedule/auto">
              <i className="bi bi-magic me-1" />
              Авто-составление
            </NavLink>
          </li>
        </ul>
        <div className="schedule-hub-body">
          <Outlet />
        </div>
      </div>
    </ScheduleExpandContext.Provider>
  )
}
