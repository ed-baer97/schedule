import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { apiJson, extractApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { AtmosphereBg } from '../components/AtmosphereBg'
import { BrandMark } from '../components/BrandMark'
import { ThemeToggle } from '../components/ThemeToggle'

type School = {
  id: number
  name: string
  slug: string
  is_active: boolean
  admins_count: number
}

type PlatformDashboard = {
  schools_total: number
  schools_active: number
  schools_inactive: number
  schools_without_admin: number
  school_admins_total: number
  school_admins_active: number
  jobs_active: number
  teachers_total: number
  classes_total: number
}

type SchoolAdmin = {
  id: number
  email: string
  role: string
  is_active: boolean
  created_at?: string | null
  password?: string | null
}

type AdminResult = {
  id: number
  email: string
  password: string
  message: string
}

function AdminFrame({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  return (
    <div className="app-shell admin-shell">
      <AtmosphereBg className="app-atmosphere" />
      <div className="app-glass" aria-hidden />
      <nav className="navbar navbar-dark app-navbar">
        <div className="container-fluid px-3">
          <span className="navbar-brand text-white d-flex align-items-center gap-2 mb-0">
            <BrandMark size={32} />
            KiVi
            <span className="fw-normal opacity-75 fs-6">Админка</span>
          </span>
          <div className="d-flex align-items-center gap-2">
            <ThemeToggle />
            {user?.email ? (
              <span className="text-white-50 small d-none d-md-inline">{user.email}</span>
            ) : null}
            <button type="button" className="btn btn-sm btn-outline-light" onClick={() => void logout()}>
              Выйти
            </button>
          </div>
        </div>
      </nav>
      <div className="app-body">
        <main className="app-main">
          <div className="app-main-scroll">
            <div className="admin-page mx-auto w-100">{children}</div>
          </div>
        </main>
      </div>
    </div>
  )
}

function CredentialsBox({
  email,
  password,
  title,
}: {
  email: string
  password: string
  title: string
}) {
  return (
    <div className="alert alert-success py-3">
      <div className="fw-semibold mb-2">{title}</div>
      <div className="small mb-1">
        Логин:{' '}
        <code className="user-select-all fs-6">{email}</code>
      </div>
      <div className="small mb-0">
        Пароль:{' '}
        <code className="user-select-all fs-6">{password}</code>
      </div>
      <div className="text-muted small mt-2 mb-0">
        Сохраните данные — после обновления страницы пароль снова не отобразится (хранится только хеш).
      </div>
    </div>
  )
}

function SchoolPanel({ schoolId }: { schoolId: number }) {
  const qc = useQueryClient()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [shown, setShown] = useState<Record<number, string>>({})
  const [lastCreated, setLastCreated] = useState<{ email: string; password: string } | null>(
    null,
  )
  const [pwdDrafts, setPwdDrafts] = useState<Record<number, string>>({})

  const adminsQuery = useQuery({
    queryKey: ['admin-school-admins', schoolId],
    queryFn: () => apiJson<SchoolAdmin[]>(`/api/admin/schools/${schoolId}/admins`),
  })

  const createAdmin = useMutation({
    mutationFn: () =>
      apiJson<AdminResult>(`/api/admin/schools/${schoolId}/admins`, {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }),
    onSuccess: (data) => {
      setError(null)
      setLastCreated({ email: data.email, password: data.password })
      setShown((prev) => ({ ...prev, [data.id]: data.password }))
      setEmail('')
      setPassword('')
      void qc.invalidateQueries({ queryKey: ['admin-school-admins', schoolId] })
      void qc.invalidateQueries({ queryKey: ['admin-schools'] })
      void qc.invalidateQueries({ queryKey: ['admin-dashboard'] })
    },
    onError: (e) => {
      setLastCreated(null)
      setError(extractApiError(e))
    },
  })

  const updateAdmin = useMutation({
    mutationFn: (payload: { id: number; password?: string; is_active?: boolean }) =>
      apiJson<SchoolAdmin>(`/api/admin/users/${payload.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          ...(payload.password !== undefined ? { password: payload.password } : {}),
          ...(payload.is_active !== undefined ? { is_active: payload.is_active } : {}),
        }),
      }),
    onSuccess: (data, vars) => {
      setError(null)
      if (vars.password) {
        setShown((prev) => ({ ...prev, [data.id]: vars.password! }))
        setLastCreated({ email: data.email, password: vars.password })
      }
      setPwdDrafts((prev) => {
        const next = { ...prev }
        delete next[vars.id]
        return next
      })
      void qc.invalidateQueries({ queryKey: ['admin-school-admins', schoolId] })
      void qc.invalidateQueries({ queryKey: ['admin-dashboard'] })
    },
    onError: (e) => {
      setLastCreated(null)
      setError(extractApiError(e))
    },
  })

  function savePassword(adminId: number, nextPassword: string) {
    const password = nextPassword.trim()
    if (password.length < 8) {
      setError('Пароль должен быть не короче 8 символов')
      return
    }
    setError(null)
    updateAdmin.mutate({ id: adminId, password })
  }

  function onCreate(e: FormEvent) {
    e.preventDefault()
    setError(null)
    createAdmin.mutate()
  }

  if (adminsQuery.isLoading) {
    return <p className="text-muted small mb-0">Загрузка админов…</p>
  }
  if (adminsQuery.isError) {
    return <p className="text-danger small mb-0">{extractApiError(adminsQuery.error)}</p>
  }

  const admins = adminsQuery.data ?? []

  return (
    <div className="pt-1">
      {error ? <div className="alert alert-danger py-2 small">{error}</div> : null}
      {lastCreated ? (
        <CredentialsBox
          title="Данные для входа"
          email={lastCreated.email}
          password={lastCreated.password}
        />
      ) : null}

      <h3 className="h6 mb-2">Админы школы</h3>
      {admins.length === 0 ? (
        <p className="text-muted small">Пока нет администраторов</p>
      ) : (
        <div className="table-responsive mb-3">
          <table className="table table-sm align-middle mb-0">
            <thead>
              <tr>
                <th>Логин</th>
                <th>Пароль</th>
                <th>Статус</th>
                <th colSpan={2}>Сменить пароль</th>
              </tr>
            </thead>
            <tbody>
              {admins.map((a) => {
                const draft = pwdDrafts[a.id] ?? ''
                return (
                  <tr key={a.id}>
                    <td>
                      <code className="user-select-all">{a.email}</code>
                    </td>
                    <td>
                      {shown[a.id] ? (
                        <code className="user-select-all">{shown[a.id]}</code>
                      ) : (
                        <span className="text-muted small">скрыт — задайте новый</span>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className={`btn btn-sm ${a.is_active ? 'btn-outline-success' : 'btn-outline-secondary'}`}
                        onClick={() =>
                          updateAdmin.mutate({ id: a.id, is_active: !a.is_active })
                        }
                        disabled={updateAdmin.isPending}
                      >
                        {a.is_active ? 'Активен' : 'Выкл'}
                      </button>
                    </td>
                    <td colSpan={2}>
                      <form
                        className="d-flex gap-2 align-items-center justify-content-end"
                        onSubmit={(e) => {
                          e.preventDefault()
                          e.stopPropagation()
                          savePassword(a.id, draft)
                        }}
                      >
                        <input
                          type="text"
                          className="form-control form-control-sm"
                          style={{ maxWidth: 220 }}
                          placeholder="новый пароль (мин. 8)"
                          value={draft}
                          onChange={(e) =>
                            setPwdDrafts((prev) => ({ ...prev, [a.id]: e.target.value }))
                          }
                          autoComplete="new-password"
                          name={`admin-password-${a.id}`}
                        />
                        <button
                          type="submit"
                          className="btn btn-sm btn-primary text-nowrap"
                          disabled={updateAdmin.isPending || draft.trim().length === 0}
                        >
                          {updateAdmin.isPending ? '…' : 'Сохранить'}
                        </button>
                      </form>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <form className="admin-create-box border rounded p-3" onSubmit={onCreate}>
        <h3 className="h6 mb-2">Создать админа школы</h3>
        <div className="row g-2 align-items-end">
          <div className="col-md-4">
            <label className="form-label small mb-1">Логин (email)</label>
            <input
              type="email"
              className="form-control form-control-sm"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="off"
            />
          </div>
          <div className="col-md-4">
            <label className="form-label small mb-1">Пароль</label>
            <input
              type="text"
              className="form-control form-control-sm"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
              placeholder="мин. 8 символов"
              autoComplete="off"
            />
          </div>
          <div className="col-md-4">
            <button
              type="submit"
              className="btn btn-success btn-sm w-100"
              disabled={createAdmin.isPending}
            >
              Создать
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}

export function AdminSchoolsPage() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<number | null>(null)

  const dashboard = useQuery({
    queryKey: ['admin-dashboard'],
    queryFn: () => apiJson<PlatformDashboard>('/api/admin/dashboard'),
  })

  const schools = useQuery({
    queryKey: ['admin-schools'],
    queryFn: () => apiJson<School[]>('/api/admin/schools'),
  })

  const createSchool = useMutation({
    mutationFn: () =>
      apiJson<School>('/api/admin/schools', {
        method: 'POST',
        body: JSON.stringify({ name, slug: slug || null }),
      }),
    onSuccess: (school) => {
      setName('')
      setSlug('')
      setError(null)
      setOpenId(school.id)
      void qc.invalidateQueries({ queryKey: ['admin-schools'] })
      void qc.invalidateQueries({ queryKey: ['admin-dashboard'] })
    },
    onError: (e) => setError(extractApiError(e)),
  })

  const toggleSchool = useMutation({
    mutationFn: (s: School) =>
      apiJson<School>(`/api/admin/schools/${s.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !s.is_active }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['admin-schools'] })
      void qc.invalidateQueries({ queryKey: ['admin-dashboard'] })
    },
    onError: (e) => setError(extractApiError(e)),
  })

  function onCreateSchool(e: FormEvent) {
    e.preventDefault()
    setError(null)
    createSchool.mutate()
  }

  if (user?.role !== 'platform_admin') {
    return (
      <AdminFrame>
        <div className="alert alert-warning">Доступ только для администратора платформы.</div>
        <Link to="/">На главную</Link>
      </AdminFrame>
    )
  }

  const d = dashboard.data
  const stats = [
    { label: 'Школы', value: d?.schools_total, hint: d ? `${d.schools_active} активных` : undefined },
    {
      label: 'Без админа',
      value: d?.schools_without_admin,
      hint: 'нужно создать доступ',
      warn: (d?.schools_without_admin ?? 0) > 0,
    },
    {
      label: 'Админы школ',
      value: d?.school_admins_active,
      hint: d ? `из ${d.school_admins_total}` : undefined,
    },
    { label: 'Учителя', value: d?.teachers_total, hint: 'по всем школам' },
    { label: 'Классы', value: d?.classes_total, hint: 'по всем школам' },
    {
      label: 'Задачи',
      value: d?.jobs_active,
      hint: 'автосоставление в работе',
    },
  ]

  return (
    <AdminFrame>
      <div className="d-flex justify-content-between align-items-start gap-2 mb-4">
        <div>
          <h1 className="h3 mb-1">Админка платформы</h1>
          <p className="text-muted mb-0 small">Сводка и управление школами / админами</p>
        </div>
      </div>

      {error ? <div className="alert alert-danger py-2">{error}</div> : null}

      <section className="mb-4">
        <h2 className="h5 mb-3">Дашборд</h2>
        {dashboard.isLoading ? (
          <p className="text-muted">Загрузка…</p>
        ) : dashboard.isError ? (
          <div className="alert alert-danger py-2">{extractApiError(dashboard.error)}</div>
        ) : (
          <div className="row g-3">
            {stats.map((stat) => (
              <div key={stat.label} className="col-6 col-md-4 col-lg">
                <div className={`card stat-card h-100 ${stat.warn ? 'border-warning' : ''}`}>
                  <div className="card-body py-3">
                    <div className="stat-label">{stat.label}</div>
                    <div className={`stat-value ${stat.warn ? 'text-warning' : ''}`}>
                      {stat.value ?? '—'}
                    </div>
                    {stat.hint ? <div className="small text-muted mt-1">{stat.hint}</div> : null}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="mb-4">
        <h2 className="h5 mb-2">Школы</h2>

        <form className="card card-body mb-3" onSubmit={onCreateSchool}>
          <div className="row g-2 align-items-end">
            <div className="col-md-5">
              <label className="form-label small mb-1">Название</label>
              <input
                className="form-control form-control-sm"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div className="col-md-4">
              <label className="form-label small mb-1">Slug (необязательно)</label>
              <input
                className="form-control form-control-sm"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="auto"
              />
            </div>
            <div className="col-md-3">
              <button className="btn btn-primary btn-sm w-100" type="submit" disabled={createSchool.isPending}>
                Добавить школу
              </button>
            </div>
          </div>
        </form>

        {schools.isLoading ? (
          <p className="text-muted">Загрузка школ…</p>
        ) : !schools.data?.length ? (
          <div className="alert alert-secondary">Пока нет школ — создайте первую выше.</div>
        ) : (
          <div className="accordion" id="schoolsAccordion">
            {schools.data.map((s) => {
              const open = openId === s.id
              return (
                <div className="accordion-item" key={s.id}>
                  <h2 className="accordion-header">
                    <button
                      className={`accordion-button ${open ? '' : 'collapsed'}`}
                      type="button"
                      onClick={() => setOpenId(open ? null : s.id)}
                    >
                      <span className="me-2 fw-semibold">{s.name}</span>
                      <span className="text-muted small me-2">{s.slug}</span>
                      {!s.is_active ? (
                        <span className="badge text-bg-secondary me-2">выкл</span>
                      ) : null}
                      {s.admins_count === 0 ? (
                        <span className="badge text-bg-warning me-2">нет админа</span>
                      ) : (
                        <span className="badge text-bg-light text-dark border me-2">
                          админов: {s.admins_count}
                        </span>
                      )}
                    </button>
                  </h2>
                  <div className={`accordion-collapse collapse ${open ? 'show' : ''}`}>
                    <div className="accordion-body">
                      <div className="d-flex justify-content-end mb-2">
                        <button
                          type="button"
                          className="btn btn-sm btn-outline-secondary"
                          onClick={() => toggleSchool.mutate(s)}
                          disabled={toggleSchool.isPending}
                        >
                          {s.is_active ? 'Отключить школу' : 'Включить школу'}
                        </button>
                      </div>
                      {open ? <SchoolPanel schoolId={s.id} /> : null}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </AdminFrame>
  )
}
