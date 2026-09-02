import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  cancelJob,
  clearSchedule,
  enqueueAutoAll,
  enqueueAutoByTeacher,
  enqueueRepair,
  fetchActiveJob,
  fetchAutoPageData,
  JobPollAborted,
  pollJob,
  stuckJobIdFromError,
  updateScheduleSettings,
  type JobOut,
  type ScheduleSettings,
  type ClassroomMode,
} from '../api/schedule'
import { extractApiError } from '../api/client'
import { DAY_NAMES_LIST, DAY_SHORT_NAMES } from '../domain/days'
import type { SchoolLevel } from '../domain/schoolLevel'

function defaultSettings(level: SchoolLevel): ScheduleSettings {
  return {
    school_level: level,
    max_lessons_per_subject_per_day: 2,
    classroom_mode: 'class_room',
    elementary_group_subjects_leave: true,
    pref_teacher_gaps: 5,
    pref_hard_subjects_early: 5,
    pref_adjacent_pairs: 5,
    pref_classroom_stability: 5,
  }
}

export function AutoSchedulerPage() {
  const qc = useQueryClient()
  const [level, setLevel] = useState<SchoolLevel>('elementary')
  const [shiftId, setShiftId] = useState<number | ''>('')
  const [timeLimit, setTimeLimit] = useState<number>(60)
  const [seed, setSeed] = useState<number>(1)
  const [hoursFirst, setHoursFirst] = useState<'more' | 'fewer'>('more')
  const [split, setSplit] = useState<'shift' | 'grade_bands'>('shift')
  const [diagnose, setDiagnose] = useState<boolean>(false)
  const [teacherId, setTeacherId] = useState<number | ''>('')
  const [running, setRunning] = useState<boolean>(false)
  const [stopping, setStopping] = useState<boolean>(false)
  const [activeJobId, setActiveJobId] = useState<number | null>(null)
  const [progress, setProgress] = useState<{ current: number; total: number; message: string }>(
    { current: 0, total: 0, message: '' },
  )
  const [log, setLog] = useState<string[]>([])
  const [elapsedSec, setElapsedSec] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [stuckJobId, setStuckJobId] = useState<number | null>(null)
  const [rulesMsg, setRulesMsg] = useState<{ kind: 'success' | 'danger'; text: string } | null>(null)
  const [clearDays, setClearDays] = useState<number[]>([])
  const logRef = useRef<HTMLDivElement | null>(null)
  const pollAbortRef = useRef<AbortController | null>(null)
  const attachedJobIdRef = useRef<number | null>(null)

  const q = useQuery({
    queryKey: ['schedule', 'auto', 'page-data'],
    queryFn: fetchAutoPageData,
  })

  const activeQ = useQuery({
    queryKey: ['jobs', 'active'],
    queryFn: fetchActiveJob,
    retry: false,
    refetchInterval: (query) => (query.state.data ? 2000 : false),
  })

  useEffect(() => {
    const list =
      q.data == null
        ? []
        : level === 'elementary'
          ? q.data.shifts_elementary
          : q.data.shifts_secondary
    if (list.length === 0) {
      setShiftId('')
      return
    }
    setShiftId((prev) => {
      if (prev !== '' && list.some((s) => s.id === prev)) return prev
      return list[0].id
    })
  }, [level, q.data])

  useEffect(() => {
    if (!rulesMsg) return
    const t = setTimeout(() => setRulesMsg(null), 4000)
    return () => clearTimeout(t)
  }, [rulesMsg])

  const saveRules = useMutation({
    mutationFn: (p: { level: SchoolLevel; payload: Partial<ScheduleSettings> }) =>
      updateScheduleSettings(p.level, p.payload),
    onSuccess: async () => {
      setRulesMsg({ kind: 'success', text: 'Правила сохранены' })
      await qc.invalidateQueries({ queryKey: ['schedule'] })
    },
    onError: (e: Error) => setRulesMsg({ kind: 'danger', text: e.message }),
  })

  useEffect(() => {
    if (!running) {
      return
    }
    setElapsedSec(0)
    const id = window.setInterval(() => setElapsedSec((s) => s + 1), 1000)
    return () => window.clearInterval(id)
  }, [running])

  function appendLog(line: string) {
    setLog((prev) => {
      const next = [...prev, line]
      if (next.length > 500) next.splice(0, next.length - 500)
      return next
    })
    requestAnimationFrame(() => {
      if (logRef.current) {
        logRef.current.scrollTop = logRef.current.scrollHeight
      }
    })
  }

  function stopPolling() {
    pollAbortRef.current?.abort()
    pollAbortRef.current = null
  }

  function resetState() {
    setError(null)
    setStuckJobId(null)
    setProgress({ current: 0, total: 0, message: '' })
    setLog([])
    setStopping(false)
    setActiveJobId(null)
  }

  function handleJobResult(job: JobOut) {
    const logDiagnostics = (src: Record<string, unknown> | null | undefined) => {
      const diags = (src?.diagnostics as { reason?: string }[] | undefined) || []
      for (const d of diags) {
        if (d?.reason) appendLog(`• ${d.reason}`)
      }
    }
    if (job.status === 'failed') {
      const msg = job.error || 'Задача завершилась с ошибкой'
      setError(msg)
      appendLog(`Не удалось составить расписание. ${msg}`)
      logDiagnostics(job.result)
      return
    }
    if (job.status === 'cancelled') {
      const count = (job.result?.count as number | undefined) ?? 0
      if (job.kind === 'auto_all') {
        appendLog('Остановлено. Сетка смены не менялась — CP-SAT записывает результат только в конце.')
      } else {
        appendLog(`Остановлено. Уже поставленные уроки сохранены (${count}).`)
      }
      return
    }
    const e = job.result || {}
    const count = e.count ?? '—'
    const wall = e.wall_time_sec as number | undefined
    appendLog(`Готово. В сетку записано уроков: ${count}.`)
    const chunks = e.chunks as number | undefined
    if (chunks != null && chunks > 1) {
      appendLog(`Смена порезана на ${chunks} куска по параллелям.`)
    }
    if (typeof wall === 'number') {
      appendLog(`Поиск занял ${Math.round(wall)} с.`)
    }
    const placed = e.solver_placed_count as number | undefined
    if (placed != null) {
      const unplaced = (e.unplaced as unknown[] | undefined)?.length ?? 0
      appendLog(`Repair: добавлено ${placed}, осталось назначений ${unplaced}.`)
    }
    const status = e.cp_sat_status as string | undefined
    if (status === 'OPTIMAL') appendLog('Найдено оптимальное расписание.')
    else if (status === 'FEASIBLE') appendLog('Найдено допустимое расписание.')
    else if (status === 'UNKNOWN') appendLog('За отведённое время решение не найдено.')
    logDiagnostics(e)
  }

  async function attachToJob(jobId: number, opts?: { resume?: boolean }) {
    if (
      attachedJobIdRef.current === jobId &&
      pollAbortRef.current &&
      !pollAbortRef.current.signal.aborted
    ) {
      return
    }
    stopPolling()
    const ac = new AbortController()
    pollAbortRef.current = ac
    attachedJobIdRef.current = jobId
    setError(null)
    setStuckJobId(null)
    setRunning(true)
    setActiveJobId(jobId)
    if (!opts?.resume) {
      setStopping(false)
    }
    if (opts?.resume) {
      appendLog(`Задача #${jobId} продолжается на сервере`)
    }
    try {
      const job = await pollJob(jobId, (p) => setProgress(p), appendLog, ac.signal)
      if (ac.signal.aborted) return
      handleJobResult(job)
      await qc.invalidateQueries({ queryKey: ['schedule'] })
      await qc.invalidateQueries({ queryKey: ['jobs'] })
    } catch (e) {
      if (e instanceof JobPollAborted || ac.signal.aborted) return
      setError(extractApiError(e))
      setStuckJobId(stuckJobIdFromError(e))
    } finally {
      if (!ac.signal.aborted) {
        setRunning(false)
        setStopping(false)
        setActiveJobId(null)
        attachedJobIdRef.current = null
      }
    }
  }

  async function startJob(start: () => Promise<{ job_id: number }>) {
    resetState()
    setRunning(true)
    try {
      const started = await start()
      appendLog(`Задача #${started.job_id} поставлена в очередь`)
      void qc.invalidateQueries({ queryKey: ['jobs', 'active'] })
      await attachToJob(started.job_id)
    } catch (e) {
      const existing = stuckJobIdFromError(e)
      if (existing != null) {
        appendLog(`Задача #${existing} уже выполняется на сервере — показываю прогресс.`)
        void qc.invalidateQueries({ queryKey: ['jobs', 'active'] })
        await attachToJob(existing)
        return
      }
      setError(extractApiError(e))
      setStuckJobId(null)
      setRunning(false)
      setStopping(false)
      setActiveJobId(null)
    }
  }

  useEffect(() => {
    return () => stopPolling()
  }, [])

  useEffect(() => {
    const job = activeQ.data
    if (job == null) return
    if (attachedJobIdRef.current === job.id) return
    void attachToJob(job.id, { resume: true })
    if (job.status === 'cancelling') setStopping(true)
    // attachToJob is recreated each render; resume only when the active id changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeQ.data?.id])

  async function runAll() {
    if (shiftId === '') {
      setError('Выберите смену')
      return
    }
    await startJob(() =>
      enqueueAutoAll({
        school_level: level,
        shift_id: Number(shiftId),
        time_limit_sec: timeLimit,
        random_seed: seed,
        diagnose,
        split,
        hours_first: hoursFirst,
      }),
    )
  }

  async function runTeacher() {
    if (teacherId === '') {
      setError('Выберите учителя')
      return
    }
    await startJob(() =>
      enqueueAutoByTeacher({
        teacher_id: Number(teacherId),
        school_level: level,
        diagnose,
      }),
    )
  }

  function toggleClearDay(day: number) {
    setClearDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day].sort((a, b) => a - b),
    )
  }

  async function doClear(
    filter: {
      school_level?: string
      class_id?: number
      teacher_id?: number
    },
    options?: { allDays?: boolean },
  ) {
    const days = options?.allDays || clearDays.length === 0 ? undefined : clearDays
    const dayLabel =
      days != null ? days.map((d) => DAY_NAMES_LIST[d - 1]).join(', ') : 'все дни'
    if (!confirm(`Очистить расписание (${dayLabel})? Удалит уроки из выбранной области.`)) return
    resetState()
    setRunning(true)
    try {
      const res = await clearSchedule({ ...filter, days_of_week: days })
      appendLog(
        days != null
          ? `Удалено уроков за ${dayLabel}: ${res.count}`
          : `Удалено уроков: ${res.count}`,
      )
      await qc.invalidateQueries({ queryKey: ['schedule'] })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  async function runRepair() {
    await startJob(() => enqueueRepair({ school_level: level }))
  }

  const stopJobId = activeJobId ?? activeQ.data?.id ?? null

  async function stopRunning(force = false) {
    if (stopJobId == null) return
    setStopping(true)
    try {
      await cancelJob(stopJobId, force)
      appendLog(force ? 'Задача сброшена.' : 'Запрошена остановка…')
      await qc.invalidateQueries({ queryKey: ['jobs'] })
    } catch (e) {
      if (!force) {
        try {
          await cancelJob(stopJobId, true)
          appendLog('Остановка не прошла — задача сброшена.')
          await qc.invalidateQueries({ queryKey: ['jobs'] })
          return
        } catch (e2) {
          setStopping(false)
          setError(e2 instanceof Error ? e2.message : String(e2))
          return
        }
      }
      setStopping(false)
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function resetStuckJob() {
    if (stuckJobId == null) return
    setStopping(true)
    try {
      await cancelJob(stuckJobId, true)
      appendLog(`Задача #${stuckJobId} сброшена. Можно запускать заново.`)
      await qc.invalidateQueries({ queryKey: ['jobs'] })
      setError(null)
      setStuckJobId(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setStopping(false)
    }
  }

  if (q.isLoading) return <p>Загрузка…</p>
  if (q.isError) return <p className="text-danger">{extractApiError(q.error)}</p>
  const data = q.data!

  const shifts = level === 'elementary' ? data.shifts_elementary : data.shifts_secondary
  const warnings = level === 'elementary' ? data.elementary_warnings : data.secondary_warnings
  const rules =
    (level === 'elementary' ? data.elementary_settings : data.secondary_settings)
    ?? defaultSettings(level)
  const percent = progress.total > 0 ? Math.min(100, Math.round((progress.current / progress.total) * 100)) : 0

  return (
    <div>
      <ul className="nav nav-tabs mb-3">
        <li className="nav-item">
          <button
            type="button"
            className={`nav-link ${level === 'elementary' ? 'active' : ''}`}
            onClick={() => setLevel('elementary')}
          >
            Начальная школа
          </button>
        </li>
        <li className="nav-item">
          <button
            type="button"
            className={`nav-link ${level === 'secondary' ? 'active' : ''}`}
            onClick={() => setLevel('secondary')}
          >
            Основная школа
          </button>
        </li>
      </ul>

      {warnings.length > 0 && (
        <div className="alert alert-warning py-2">
          <strong>{warnings.length}</strong> предупреждений по кабинетам:
          <ul className="mb-0 small">
            {warnings.slice(0, 5).map((w, i) => (
              <li key={i}>{w.message}</li>
            ))}
          </ul>
        </div>
      )}

      {rulesMsg && <div className={`alert alert-${rulesMsg.kind} py-2`}>{rulesMsg.text}</div>}

      <RulesCard
        key={level}
        level={level}
        initial={rules}
        disabled={saveRules.isPending || running}
        onSave={(payload) => saveRules.mutate({ level, payload })}
      />

      <div className="row g-3 mt-0">
        <div className="col-md-6">
          <div className="card shadow-sm h-100">
            <div className="card-header fw-semibold">Заполнить всё (CP-SAT, одна смена)</div>
            <div className="card-body">
              <div className="row g-2">
                <div className="col-md-6">
                  <label className="form-label small">Смена</label>
                  <select
                    className="form-select"
                    value={shiftId === '' ? '' : String(shiftId)}
                    onChange={(e) => setShiftId(e.target.value === '' ? '' : Number(e.target.value))}
                  >
                    <option value="">—</option>
                    {shifts.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>
                <div className="col-md-6">
                  <label className="form-label small">Время поиска, сек</label>
                  <input
                    type="number"
                    className="form-control"
                    min={1}
                    max={86400}
                    step={1}
                    value={timeLimit}
                    onChange={(e) => {
                      const n = Number(e.target.value)
                      setTimeLimit(Number.isFinite(n) && n >= 1 ? Math.floor(n) : 1)
                    }}
                  />
                  <div className="form-text">
                    Сколько секунд решатель ищет расписание. Если допустимое нашлось раньше —
                    оставшееся время идёт на улучшение.
                  </div>
                </div>
                <div className="col-12">
                  <label className="form-label small">Область CP-SAT</label>
                  <div className="form-check">
                    <input
                      className="form-check-input"
                      type="radio"
                      name="cpSatSplit"
                      id="splitWhole"
                      checked={split === 'shift'}
                      onChange={() => setSplit('shift')}
                    />
                    <label className="form-check-label" htmlFor="splitWhole">
                      Вся смена
                    </label>
                  </div>
                  <div className="form-check">
                    <input
                      className="form-check-input"
                      type="radio"
                      name="cpSatSplit"
                      id="splitBands"
                      checked={split === 'grade_bands'}
                      onChange={() => setSplit('grade_bands')}
                    />
                    <label className="form-check-label" htmlFor="splitBands">
                      Порезать смену
                    </label>
                  </div>
                </div>
                <div className="col-12 mt-1">
                  <details className="border rounded p-2 bg-light bg-opacity-50">
                    <summary className="small text-muted fw-semibold" style={{ cursor: 'pointer' }}>
                      Дополнительно (seed, порядок часов, диагностика)
                    </summary>
                    <div className="row g-2 mt-1 pt-1 border-top">
                      <div className="col-md-6">
                        <label className="form-label small">Random seed</label>
                        <input
                          type="number"
                          className="form-control form-control-sm"
                          value={seed}
                          onChange={(e) => setSeed(Number(e.target.value) || 1)}
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label small">Порядок предметов</label>
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="radio"
                            name="hoursFirst"
                            id="hoursMore"
                            checked={hoursFirst === 'more'}
                            onChange={() => setHoursFirst('more')}
                          />
                          <label className="form-check-label small" htmlFor="hoursMore">
                            Сначала больше часов в неделю
                          </label>
                        </div>
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="radio"
                            name="hoursFirst"
                            id="hoursFewer"
                            checked={hoursFirst === 'fewer'}
                            onChange={() => setHoursFirst('fewer')}
                          />
                          <label className="form-check-label small" htmlFor="hoursFewer">
                            Сначала меньше часов в неделю
                          </label>
                        </div>
                      </div>
                      <div className="col-12 form-check ms-2 mt-1">
                        <input
                          className="form-check-input"
                          type="checkbox"
                          id="diagnoseAll"
                          checked={diagnose}
                          onChange={(e) => setDiagnose(e.target.checked)}
                        />
                        <label className="form-check-label small" htmlFor="diagnoseAll">
                          Диагностика остатка
                        </label>
                      </div>
                    </div>
                  </details>
                </div>
              </div>
              <div className="mt-3">
                <div className="small text-muted mb-1">Дни для очистки</div>
                <div className="d-flex flex-wrap gap-1" role="group" aria-label="Дни для очистки">
                  {DAY_SHORT_NAMES.map((label, i) => {
                    const day = i + 1
                    const on = clearDays.includes(day)
                    return (
                      <button
                        key={day}
                        type="button"
                        className={`btn btn-sm ${on ? 'btn-danger' : 'btn-outline-secondary'}`}
                        disabled={running}
                        aria-pressed={on}
                        onClick={() => toggleClearDay(day)}
                      >
                        {label}
                      </button>
                    )
                  })}
                </div>
                <div className="form-text mb-2">
                  {clearDays.length === 0
                    ? 'Не выбрано — очистка удалит уроки за всю неделю.'
                    : `Будут удалены уроки: ${clearDays.map((d) => DAY_NAMES_LIST[d - 1]).join(', ')}.`}
                </div>
              </div>
              <div className="d-flex gap-2 flex-wrap">
                <button
                  type="button"
                  className="btn btn-success"
                  disabled={running}
                  onClick={runAll}
                >
                  Запустить
                </button>
                <button
                  type="button"
                  className="btn btn-outline-success"
                  disabled={running}
                  onClick={runRepair}
                >
                  Repair (дозаполнить)
                </button>
                <button
                  type="button"
                  className="btn btn-outline-danger"
                  disabled={running}
                  onClick={() => doClear({ school_level: level })}
                >
                  {clearDays.length === 0 ? 'Очистить уровень' : 'Очистить выбранные дни'}
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="col-md-6">
          <div className="card shadow-sm h-100">
            <div className="card-header fw-semibold">Заполнить по учителю (лесенка)</div>
            <div className="card-body">
              <label className="form-label small">Учитель</label>
              <select
                className="form-select mb-3"
                value={teacherId === '' ? '' : String(teacherId)}
                onChange={(e) => setTeacherId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                <option value="">—</option>
                {data.teachers.map((t) => (
                  <option key={t.id} value={t.id}>{t.full_name}</option>
                ))}
              </select>
              <div className="d-flex gap-2">
                <button
                  type="button"
                  className="btn btn-success"
                  disabled={running || teacherId === ''}
                  onClick={runTeacher}
                >
                  Запустить
                </button>
                <button
                  type="button"
                  className="btn btn-outline-danger"
                  disabled={running || teacherId === ''}
                  onClick={() =>
                    doClear({ school_level: level, teacher_id: Number(teacherId) }, { allDays: true })
                  }
                >
                  Очистить уроки учителя
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="card shadow-sm mt-3">
        <div className="card-header d-flex justify-content-between align-items-center">
          <span className="fw-semibold">Прогресс</span>
          <div className="d-flex align-items-center gap-2">
            {running && (
              <span className="text-muted small">
                {stopping ? 'останавливается…' : 'выполняется на сервере…'}
              </span>
            )}
            {running && (
              <button
                type="button"
                className="btn btn-sm btn-outline-danger"
                disabled={stopJobId == null}
                onClick={() => void stopRunning(stopping)}
              >
                {stopping ? 'Сбросить' : 'Остановить'}
              </button>
            )}
          </div>
        </div>
        <div className="card-body">
          <div className="progress mb-2" role="progressbar" aria-label="Progress">
            <div
              className="progress-bar"
              style={{ width: `${percent}%` }}
            >
              {percent}%
            </div>
          </div>
          {progress.message && (
            <div className="small text-muted mb-2">
              {progress.message}
              {running && elapsedSec > 0 ? ` · ${elapsedSec} с` : ''}
            </div>
          )}
          {running && (
            <div className="small text-muted mb-2">
              Можно открыть другую страницу — расчёт продолжится. Вернитесь сюда, чтобы увидеть прогресс.
            </div>
          )}
          {error && (
            <div className="alert alert-danger py-2">
              <div>{error}</div>
              {stuckJobId != null && (
                <button
                  type="button"
                  className="btn btn-sm btn-outline-danger mt-2"
                  disabled={stopping}
                  onClick={() => void resetStuckJob()}
                >
                  Сбросить задачу #{stuckJobId}
                </button>
              )}
            </div>
          )}
          <div
            ref={logRef}
            className="border rounded p-2 small bg-light"
            style={{ maxHeight: 280, overflow: 'auto', fontFamily: 'monospace' }}
          >
            {log.length === 0 ? (
              <span className="text-muted">Лог пуст. Запустите авто-составление.</span>
            ) : (
              log.map((line, i) => <div key={i}>{line}</div>)
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function RulesCard(props: {
  level: SchoolLevel
  initial: ScheduleSettings
  disabled: boolean
  onSave: (p: Partial<ScheduleSettings>) => void
}) {
  const { level, initial, disabled, onSave } = props
  const showGroupLeave = level === 'elementary'
  const [mode, setMode] = useState<ClassroomMode>(initial.classroom_mode)
  const [groupLeave, setGroupLeave] = useState(initial.elementary_group_subjects_leave)
  const [prefGaps, setPrefGaps] = useState(initial.pref_teacher_gaps ?? 5)
  const [prefEarly, setPrefEarly] = useState(initial.pref_hard_subjects_early ?? 5)
  const [prefPairs, setPrefPairs] = useState(initial.pref_adjacent_pairs ?? 5)
  const [prefRooms, setPrefRooms] = useState(initial.pref_classroom_stability ?? 5)

  useEffect(() => {
    setMode(initial.classroom_mode)
    setGroupLeave(initial.elementary_group_subjects_leave)
    setPrefGaps(initial.pref_teacher_gaps ?? 5)
    setPrefEarly(initial.pref_hard_subjects_early ?? 5)
    setPrefPairs(initial.pref_adjacent_pairs ?? 5)
    setPrefRooms(initial.pref_classroom_stability ?? 5)
  }, [
    initial.classroom_mode,
    initial.elementary_group_subjects_leave,
    initial.pref_teacher_gaps,
    initial.pref_hard_subjects_early,
    initial.pref_adjacent_pairs,
    initial.pref_classroom_stability,
  ])

  return (
    <div className="card shadow-sm mb-3">
      <div className="card-header fw-semibold">Правила</div>
      <div className="card-body">
        <p className="text-muted small mb-3">
          Учебные дни в неделю и максимум уроков в день задаются в настройках каждой{' '}
          <Link to="/shifts">смены</Link>.
        </p>
        <div className="row g-2">
          <div className="col-md-6">
            <label className="form-label small">Режим кабинетов</label>
            <select
              className="form-select"
              value={mode}
              onChange={(e) => setMode(e.target.value as ClassroomMode)}
            >
              <option value="class_room">Учитель приходит к классу</option>
              <option value="teacher_room">Дети приходят к учителю</option>
            </select>
          </div>
          {showGroupLeave && (
            <div className="col-md-6 d-flex align-items-center mt-3 mt-md-0">
              <div className="form-check ms-2 mt-md-3">
                <input
                  className="form-check-input"
                  type="checkbox"
                  id="group-leave-auto"
                  checked={groupLeave}
                  onChange={(e) => setGroupLeave(e.target.checked)}
                />
                <label className="form-check-label" htmlFor="group-leave-auto">
                  Групповые уроки: дети уходят к учителю
                </label>
              </div>
            </div>
          )}
          <div className="col-12 mt-3">
            <div className="fw-semibold small mb-2">Предпочтения автосоставления (0 — не важно, 10 — важно)</div>
            <div className="row g-2">
              <PrefSlider
                id="pref-gaps"
                label="Без окон у учителя"
                value={prefGaps}
                onChange={setPrefGaps}
              />
              <PrefSlider
                id="pref-early"
                label="Сложные предметы раньше"
                value={prefEarly}
                onChange={setPrefEarly}
              />
              <PrefSlider
                id="pref-pairs"
                label="Сдвоенные уроки рядом"
                value={prefPairs}
                onChange={setPrefPairs}
              />
              <PrefSlider
                id="pref-rooms"
                label="Стабильность кабинетов / баланс дней"
                value={prefRooms}
                onChange={setPrefRooms}
              />
            </div>
          </div>
        </div>
        <button
          type="button"
          className="btn btn-primary mt-3"
          disabled={disabled}
          onClick={() =>
            onSave({
              max_lessons_per_subject_per_day: 2,
              classroom_mode: mode,
              elementary_group_subjects_leave: showGroupLeave ? groupLeave : undefined,
              pref_teacher_gaps: prefGaps,
              pref_hard_subjects_early: prefEarly,
              pref_adjacent_pairs: prefPairs,
              pref_classroom_stability: prefRooms,
            })
          }
        >
          Сохранить
        </button>
      </div>
    </div>
  )
}

function PrefSlider(props: {
  id: string
  label: string
  value: number
  onChange: (n: number) => void
}) {
  const { id, label, value, onChange } = props
  return (
    <div className="col-md-6">
      <label className="form-label small d-flex justify-content-between" htmlFor={id}>
        <span>{label}</span>
        <span className="text-muted">{value}</span>
      </label>
      <input
        id={id}
        type="range"
        className="form-range"
        min={0}
        max={10}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  )
}
