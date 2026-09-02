import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listSchoolClasses } from '../api/schoolClasses'
import { listTeachers } from '../api/teachers'
import {
  exportAllUrl,
  exportClassUrl,
  exportTeacherUrl,
} from '../api/reports'
import { PageHeader } from '../components/PageHeader'
import { ScheduleExcelImport } from '../components/ScheduleExcelImport'

export function ReportsPage() {
  const [classId, setClassId] = useState<number | ''>('')
  const [teacherId, setTeacherId] = useState<number | ''>('')
  const [teacherQuery, setTeacherQuery] = useState('')

  const classesQ = useQuery({
    queryKey: ['school-classes'],
    queryFn: listSchoolClasses,
  })
  const teachersQ = useQuery({
    queryKey: ['teachers'],
    queryFn: listTeachers,
  })

  const classes = useMemo(() => classesQ.data ?? [], [classesQ.data])
  const teachers = teachersQ.data ?? []
  const teacherOptions = useMemo(() => {
    const q = teacherQuery.trim().toLowerCase()
    const list = q
      ? teachers.filter((t) => t.full_name.toLowerCase().includes(q))
      : teachers
    if (teacherId !== '' && !list.some((t) => t.id === teacherId)) {
      const selected = teachers.find((t) => t.id === teacherId)
      if (selected) return [selected, ...list]
    }
    return list
  }, [teachers, teacherQuery, teacherId])

  return (
    <div>
      <PageHeader
        title="Отчёты и экспорт"
        subtitle="Печать и Excel: полное расписание, класс или учитель"
      />
      <div className="row g-3">
        <div className="col-md-6">
          <div className="card shadow-sm h-100 report-pick-card">
            <div className="card-header fw-semibold">
              <i className="bi bi-file-earmark-spreadsheet" />
              Экспорт полного расписания
            </div>
            <div className="card-body d-grid gap-2">
              <a className="btn btn-success" href={exportAllUrl('elementary')}>
                Начальная школа (Excel)
              </a>
              <a
                className="btn"
                style={{ background: '#9b59b6', color: 'white' }}
                href={exportAllUrl('secondary')}
              >
                Основная школа (Excel)
              </a>
              <hr className="my-2" />
              <p className="small text-muted mb-2">
                Если сетку очистили — загрузите тот же Excel, уроки встанут обратно.
              </p>
              <ScheduleExcelImport compact />
            </div>
          </div>
        </div>

        <div className="col-md-6">
          <div className="card shadow-sm h-100 report-pick-card">
            <div className="card-header fw-semibold">
              <i className="bi bi-people" />
              Расписание класса
            </div>
            <div className="card-body">
              <p className="report-pick-hint">Звонки и перемены в сетке просмотра.</p>
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
                  href={classId === '' ? '#' : exportClassUrl(classId)}
                  className={`btn btn-outline-success flex-fill ${classId === '' ? 'disabled' : ''}`}
                >
                  Excel
                </a>
              </div>
            </div>
          </div>
        </div>

        <div className="col-md-6">
          <div className="card shadow-sm h-100 report-pick-card">
            <div className="card-header fw-semibold">
              <i className="bi bi-person-badge" />
              Расписание учителя
            </div>
            <div className="card-body">
              <p className="report-pick-hint">
                В сетке — время уроков и перемен; в Excel та же недельная таблица.
              </p>
              <input
                className="form-control mb-2"
                type="search"
                placeholder="Поиск по ФИО…"
                value={teacherQuery}
                onChange={(e) => setTeacherQuery(e.target.value)}
                aria-label="Поиск учителя"
              />
              <select
                className="form-select mb-3"
                value={teacherId === '' ? '' : String(teacherId)}
                onChange={(e) =>
                  setTeacherId(e.target.value === '' ? '' : Number(e.target.value))
                }
              >
                <option value="">Выберите учителя…</option>
                {teacherOptions.map((t) => (
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
                  href={teacherId === '' ? '#' : exportTeacherUrl(teacherId)}
                  className={`btn btn-outline-success flex-fill ${teacherId === '' ? 'disabled' : ''}`}
                >
                  Excel
                </a>
              </div>
            </div>
          </div>
        </div>

        <div className="col-md-6">
          <div className="card shadow-sm h-100 report-pick-card">
            <div className="card-header fw-semibold">
              <i className="bi bi-printer" />
              Печать
            </div>
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
