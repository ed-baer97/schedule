import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { apiJson, extractApiError } from '../api/client'
import { useAuth, type AuthUser } from '../auth/AuthContext'
import { PublicLayout } from '../components/PublicLayout'

const FEATURES = [
  {
    icon: 'bi-magic',
    title: 'Автосоставление',
    text: 'Решатель сам расставляет уроки с учётом учителей, кабинетов и смен — без двойных назначений.',
  },
  {
    icon: 'bi-arrows-move',
    title: 'Ручная сетка',
    text: 'Перетаскивайте уроки, правьте ячейки и сразу видите конфликты: учитель, класс, кабинет.',
  },
  {
    icon: 'bi-file-earmark-excel',
    title: 'Импорт и отчёты',
    text: 'Загрузите учителей и учебный план из Excel, выгрузите готовое расписание для печати.',
  },
  {
    icon: 'bi-people',
    title: 'Подгруппы',
    text: 'Два учителя на один предмет в классе — отдельные группы в одной клетке расписания.',
  },
  {
    icon: 'bi-clock-history',
    title: 'Смены и звонки',
    text: 'Начальная и основная школа, свои сетки уроков и расписание звонков на каждую смену.',
  },
]

const STEPS = [
  { title: 'Данные', text: 'Импорт Excel или справочники вручную: учителя, кабинеты, предметы.' },
  { title: 'Нагрузка', text: 'Назначьте часы классам и учителям, отметьте подгруппы.' },
  { title: 'Сетка', text: 'Соберите расписание руками или запустите автосоставление.' },
  { title: 'Отчёты', text: 'Проверьте конфликты и выгрузите Excel для учителей и классов.' },
]

export function LoginPage() {
  const { user, loading, setUser } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!loading && user) {
    return (
      <Navigate
        to={user.role === 'platform_admin' && !user.school_id ? '/admin' : '/'}
        replace
      />
    )
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const me = await apiJson<AuthUser>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
      setUser(me)
      navigate(me.role === 'platform_admin' && !me.school_id ? '/admin' : '/')
    } catch (err) {
      setError(extractApiError(err))
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <PublicLayout active="login">
        <p className="text-center py-5 mb-0" style={{ color: 'rgba(244,239,228,0.7)' }}>
          Загрузка сессии…
        </p>
      </PublicLayout>
    )
  }

  return (
    <PublicLayout active="login">
      <section className="landing-hero">
        <div>
          <div className="landing-kicker">
            <i className="bi bi-calendar3" />
            Для школы, а не для IT-отдела
          </div>
          <h1 className="landing-title">
            Расписание без хаоса и <em>без конфликтов</em>
          </h1>
          <p className="landing-lead">
            Соберите сетку за день, а не за неделю: автосборка учитывает учителей, кабинеты и
            смены, а ручная правка сразу показывает пересечения.
          </p>
          <ul className="landing-points">
            <li>
              <i className="bi bi-check2-circle" />
              Автосоставление в одной сетке
            </li>
            <li>
              <i className="bi bi-check2-circle" />
              Импорт учебного плана из Excel и отчёты на выход
            </li>
          </ul>
        </div>

        <div className="landing-card-wrap" id="login">
          <div className="landing-card-glow" aria-hidden />
          <div className="landing-card">
            <h2>Вход в систему</h2>
            <p className="landing-card-sub">Администратор школы или платформы</p>
            {error ? <div className="alert alert-danger py-2">{error}</div> : null}
            <form onSubmit={onSubmit}>
              <div className="mb-3">
                <label className="form-label" htmlFor="login-email">
                  Email
                </label>
                <input
                  id="login-email"
                  type="email"
                  className="form-control"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="username"
                  placeholder="admin@school.ru"
                />
              </div>
              <div className="mb-3">
                <label className="form-label" htmlFor="login-password">
                  Пароль
                </label>
                <input
                  id="login-password"
                  type="password"
                  className="form-control"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
              </div>
              <button type="submit" className="btn btn-enter w-100" disabled={busy}>
                {busy ? 'Вход…' : 'Войти'}
              </button>
            </form>
            <p className="landing-card-foot mb-0">
              Логин и пароль выдаёт администратор платформы.
            </p>
          </div>
        </div>
      </section>

      <section className="landing-features" id="features">
        <div className="landing-features-inner">
          <h2 className="landing-section-title">Что умеет система</h2>
          <p className="landing-section-lead">
            Полный цикл: от справочников до готового расписания и выгрузки для учителей.
          </p>
          <div className="landing-feature-grid">
            {FEATURES.map((f) => (
              <article key={f.title} className="landing-feature">
                <i className={`bi ${f.icon}`} />
                <h3>{f.title}</h3>
                <p>{f.text}</p>
              </article>
            ))}
          </div>

          <h2 className="landing-section-title mt-5">Как это работает</h2>
          <p className="landing-section-lead">Четыре шага, которые завуч проходит без длинной инструкции.</p>
          <div className="landing-steps">
            {STEPS.map((s, i) => (
              <article key={s.title} className="landing-step">
                <span className="landing-step-n">{i + 1}</span>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
    </PublicLayout>
  )
}
