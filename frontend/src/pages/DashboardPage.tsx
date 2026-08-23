import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { PageHeader } from '../components/PageHeader'
import { apiJson } from '../api/client'

type Stats = {
  teachers_count: number
  classes_count: number
  subjects_count: number
  classrooms_count: number
  elementary_classes: number
  secondary_classes: number
  elementary_assignments: number
  secondary_assignments: number
  elementary_scheduled: number
  secondary_scheduled: number
}

const QUICK_LINKS = [
  { to: '/import', icon: 'bi-file-earmark-excel', label: 'Импорт Excel', desc: 'Нагрузка по предметам и кабинеты' },
  { to: '/workload', icon: 'bi-table', label: 'Нагрузка', desc: 'Часы по классам' },
  { to: '/subjects', icon: 'bi-journal-text', label: 'Предметы', desc: 'Справочник и назначения' },
  { to: '/schedule', icon: 'bi-calendar3', label: 'Расписание', desc: 'Сетка и авто-составление' },
  { to: '/reports', icon: 'bi-printer', label: 'Отчёты', desc: 'Печать и Excel' },
]

export function DashboardPage() {
  const q = useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: () => apiJson<Stats>('/api/dashboard/stats'),
  })

  if (q.isLoading) return <p className="text-muted">Загрузка…</p>
  if (q.isError) return <p className="text-danger">Ошибка: {(q.error as Error).message}</p>
  const s = q.data!

  return (
    <div className="dashboard-page">
      <PageHeader title="Главная" subtitle="Сводка по школе и быстрый переход к разделам" />

      <div className="row g-3 mb-4">
        {QUICK_LINKS.map((item) => (
          <div key={item.to} className="col-sm-6 col-lg-4">
            <Link to={item.to} className="card quick-link-card text-decoration-none h-100">
              <div className="card-body d-flex gap-3 align-items-start">
                <span className="quick-link-icon">
                  <i className={`bi ${item.icon}`} />
                </span>
                <div>
                  <div className="quick-link-title">{item.label}</div>
                  <div className="quick-link-desc">{item.desc}</div>
                </div>
              </div>
            </Link>
          </div>
        ))}
      </div>

      <div className="row g-3 mb-4">
        {[
          { label: 'Учителя', value: s.teachers_count },
          { label: 'Классы', value: s.classes_count },
          { label: 'Предметы', value: s.subjects_count },
          { label: 'Кабинеты', value: s.classrooms_count },
        ].map((stat) => (
          <div key={stat.label} className="col-6 col-md-3">
            <div className="card stat-card h-100">
              <div className="card-body">
                <div className="stat-label">{stat.label}</div>
                <div className="stat-value">{stat.value}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <h2 className="h5 mb-3">По уровням</h2>
      <div className="row g-3">
        <div className="col-md-6">
          <div className="card h-100">
            <div className="card-header">Начальная школа</div>
            <ul className="list-group list-group-flush">
              <li className="list-group-item d-flex justify-content-between">
                <span>Классов</span>
                <strong>{s.elementary_classes}</strong>
              </li>
              <li className="list-group-item d-flex justify-content-between">
                <span>Назначений</span>
                <strong>{s.elementary_assignments}</strong>
              </li>
              <li className="list-group-item d-flex justify-content-between">
                <span>Ячеек в расписании</span>
                <strong>{s.elementary_scheduled}</strong>
              </li>
            </ul>
          </div>
        </div>
        <div className="col-md-6">
          <div className="card h-100">
            <div className="card-header">Основная школа</div>
            <ul className="list-group list-group-flush">
              <li className="list-group-item d-flex justify-content-between">
                <span>Классов</span>
                <strong>{s.secondary_classes}</strong>
              </li>
              <li className="list-group-item d-flex justify-content-between">
                <span>Назначений</span>
                <strong>{s.secondary_assignments}</strong>
              </li>
              <li className="list-group-item d-flex justify-content-between">
                <span>Ячеек в расписании</span>
                <strong>{s.secondary_scheduled}</strong>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
