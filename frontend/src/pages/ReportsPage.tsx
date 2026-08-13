import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiJson } from '../api/client'

type ClassBrief = { id: number; name: string; school_level: string }
type TeacherBrief = { id: number; full_name: string }

export function ReportsPage() {
  const [classId, setClassId] = useState<number | ''>('')
  const [teacherId, setTeacherId] = useState<number | ''>('')

  const classesQ = useQuery({
    queryKey: ['school-classes'],
    queryFn: () => apiJson<ClassBrief[]>('/api/school-classes/'),
  })
  const teachersQ = useQuery({
    queryKey: ['teachers'],
    queryFn: () => apiJson<TeacherBrief[]>('/api/teachers/'),
  })

  const classes = useMemo(() => classesQ.data ?? [], [classesQ.data])
  const teachers = teachersQ.data ?? []

  return (
    <div>
      <h1 className="h3 mb-3">Отчёты и экспорт</h1>
      <div className="row g-3">
        <div className="col-md-6">
          <div className="card shadow-sm h-100">
            <div className="card-header fw-semibold">Экспорт полного расписания</div>
            <div className="card-body d-grid gap-2">
              <a
                className="btn btn-success"
                href="/api/reports/export/all/elementary"
              >
                Начальная школа (Excel)
              </a>
              <a
                className="btn"
                style={{ background: '#9b59b6', color: 'white' }}
                href="/api/reports/export/all/secondary"
              >
                Основная школа (Excel)
              </a>
            </div>
          </div>
        </div>

        <div className="col-md-6">
          <div className="card shadow-sm h-100">
            <div className="card-header fw-semibold">Расписание класса</div>
            <div className="card-body">
              <select
                className="form-select mb-3"
                value={classId === '' ? '' : String(classId)}
                onChange={(e) =>
                  setClassId(e.target.value === '' ? '' : Number(e.target.value))
                }
              >
                <option value="">Выберите класс…</option>
                {classes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.school_level === 'elementary' ? 'нач.' : 'осн.'})
                  </option>
                ))}
              </select>
              <div className="d-flex gap-2">
                <Link
                  to={classId === '' ? '#' : `/reports/class/${classId}`}
                  className={`btn btn-outline-primary flex-fill ${classId === '' ? 'disabled' : ''}`}
                >
                  Просмотр
                </Link>
                <a
                  href={classId === '' ? '#' : `/api/reports/export/class/${classId}`}
                  className={`btn btn-outline-success flex-fill ${classId === '' ? 'disabled' : ''}`}
                >
                  Excel
                </a>
              </div>
            </div>
          </div>
        </div>

        <div className="col-md-6">
          <div className="card shadow-sm h-100">
            <div className="card-header fw-semibold">Расписание учителя</div>
            <div className="card-body">
              <select
                className="form-select mb-3"
                value={teacherId === '' ? '' : String(teacherId)}
                onChange={(e) =>
                  setTeacherId(e.target.value === '' ? '' : Number(e.target.value))
                }
              >
                <option value="">Выберите учителя…</option>
                {teachers.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.full_name}
                  </option>
                ))}
              </select>
              <div className="d-flex gap-2">
                <Link
                  to={teacherId === '' ? '#' : `/reports/teacher/${teacherId}`}
                  className={`btn btn-outline-primary flex-fill ${teacherId === '' ? 'disabled' : ''}`}
                >
                  Просмотр
                </Link>
                <a
                  href={teacherId === '' ? '#' : `/api/reports/export/teacher/${teacherId}`}
                  className={`btn btn-outline-success flex-fill ${teacherId === '' ? 'disabled' : ''}`}
                >
                  Excel
                </a>
              </div>
            </div>
          </div>
        </div>

        <div className="col-md-6">
          <div className="card shadow-sm h-100">
            <div className="card-header fw-semibold">Печать</div>
            <div className="card-body">
              <p className="text-muted small mb-2">
                Откройте просмотр класса/учителя и нажмите <kbd>Ctrl</kbd>+<kbd>P</kbd>.
              </p>
              <p className="text-muted small mb-0">
                Либо экспортируйте в Excel и распечатайте оттуда.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
