import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { OverlayScrollArea } from '../components/OverlayScrollArea'
import { ModalPortal } from '../components/ModalPortal'
import { extractApiError } from '../api/client'
import {
  createScheduleCell,
  deleteScheduleCell,
  explainSlot,
  fetchAssignmentsForClass,
  fetchGrid,
  updateScheduleCell,
  type ScheduleCell as CellOut,
} from '../api/schedule'
import type { SchoolLevel } from '../domain/schoolLevel'
import { useScheduleExpand } from '../layouts/ScheduleLayout'

type SlotKey = { class_id: number; day: number; lesson: number; class_name: string }

if (typeof window !== 'undefined') {
  try {
    window.history.scrollRestoration = 'manual'
  } catch {
    /* ignore */
  }
}

const bootAnchor = typeof window !== 'undefined' ? window.location.hash.replace(/^#/, '') : ''

function dayAnchor(day: number) {
  return `day-${day}`
}

function slotAnchor(classId: number, day: number, lesson: number) {
  return `slot-${classId}-${day}-${lesson}`
}

function classAnchor(classId: number) {
  return `class-${classId}`
}

function splitBellLabel(label: string): [string, string] | null {
  const idx = label.search(/[–—-]/)
  if (idx <= 0) return null
  const start = label.slice(0, idx).trim()
  const end = label.slice(idx + 1).trim()
  if (!start || !end) return null
  return [start, end]
}

function BellLabel({ time }: { time: string }) {
  const parts = splitBellLabel(time)
  return (
    <div className="schedule-bell" title={`Звонок ${time}`}>
      {parts ? (
        <>
          <span className="schedule-bell-start">{parts[0]}</span>
          <span className="schedule-bell-dash" aria-hidden>
            –
          </span>
          <span className="schedule-bell-end">{parts[1]}</span>
        </>
      ) : (
        <span className="schedule-bell-start">{time}</span>
      )}
    </div>
  )
}

function teacherHoverKey(cell: Pick<CellOut, 'teacher_id' | 'teacher_name'>) {
  if (cell.teacher_id != null) return `id-${cell.teacher_id}`
  const name = (cell.teacher_name ?? '').trim()
  return name ? `name-${name}` : ''
}

function suppressCardDrag(ev: ReactPointerEvent<HTMLElement>) {
  ev.stopPropagation()
  const card = (ev.currentTarget as HTMLElement).closest('.lesson-card') as HTMLElement | null
  if (!card) return
  card.draggable = false
  const restore = () => {
    card.draggable = true
    window.removeEventListener('pointerup', restore)
  }
  window.addEventListener('pointerup', restore)
}

function buildTeacherHoverCss(keys: string[]) {
  const esc = (s: string) => (typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(s) : s)
  return keys
    .map((key) => {
      const a = esc(key)
      const table = `.schedule-grid-table:has(.lesson-card[data-teacher-key="${a}"]:hover)`
      const match = `.lesson-card[data-teacher-key="${a}"]`
      return `${table} ${match}{background:color-mix(in srgb, var(--kivi-primary) 22%, var(--kivi-surface))!important;box-shadow:inset 0 0 0 3px var(--kivi-primary);opacity:1;position:relative;z-index:2}
${table} ${match} .teacher-name{color:var(--kivi-primary-deep);font-weight:700}
${table} .lesson-card:not(${match}){opacity:.32}
${table} td:has(${match}){background:color-mix(in srgb, var(--kivi-primary) 10%, transparent)}`
    })
    .join('\n')
}

function applyTeacherHover(root: HTMLElement | null, key: string | null) {
  if (!root) return
  const prev = root.getAttribute('data-hover-teacher')
  if ((key ?? '') === (prev ?? '')) return
  if (key) root.setAttribute('data-hover-teacher', key)
  else root.removeAttribute('data-hover-teacher')
  root.classList.toggle('is-teacher-hover', Boolean(key))
  root.querySelectorAll<HTMLElement>('.lesson-card[data-teacher-key]').forEach((el) => {
    el.classList.toggle('teacher-highlight', Boolean(key) && el.dataset.teacherKey === key)
  })
}

function replaceHash(id: string) {
  const hash = id ? `#${id}` : ''
  const next = `${window.location.pathname}${window.location.search}${hash}`
  window.history.replaceState(null, '', next)
}

function saveTab(level: string, shiftId: number | null) {
  try {
    sessionStorage.setItem(
      'schedule:tab',
      JSON.stringify({ school_level: level, shift_id: shiftId }),
    )
  } catch {
    /* ignore */
  }
}

function loadTab(): { school_level: SchoolLevel; shift_id: number | null } | null {
  try {
    const raw = sessionStorage.getItem('schedule:tab')
    if (!raw) return null
    const v = JSON.parse(raw) as { school_level?: string; shift_id?: number | null }
    const school_level: SchoolLevel = v.school_level === 'secondary' ? 'secondary' : 'elementary'
    const shift_id =
      typeof v.shift_id === 'number' && v.shift_id > 0 ? v.shift_id : null
    return { school_level, shift_id }
  } catch {
    return null
  }
}

function viewStorageKey(level: string, shiftId: number | null) {
  return `schedule:view:${level}:${shiftId ?? 'auto'}`
}

type SavedView = { hash: string; top: number; left: number }

function loadSavedView(level: string, shiftId: number | null): SavedView | null {
  try {
    const raw = sessionStorage.getItem(viewStorageKey(level, shiftId))
    if (!raw) return null
    const v = JSON.parse(raw) as SavedView
    if (!v || typeof v.top !== 'number' || typeof v.left !== 'number') return null
    return { hash: typeof v.hash === 'string' ? v.hash : '', top: v.top, left: v.left }
  } catch {
    return null
  }
}

function saveSavedView(level: string, shiftId: number | null, v: SavedView) {
  try {
    sessionStorage.setItem(viewStorageKey(level, shiftId), JSON.stringify(v))
  } catch {
    /* ignore */
  }
}

function viewportReady(viewport: HTMLElement) {
  return viewport.clientHeight >= 40 && viewport.scrollHeight > 0
}

function scrollScheduleAnchor(id: string, align: 'start' | 'nearest' = 'nearest') {
  const target = document.getElementById(id)
  const viewport = target?.closest('.overlay-scroll-viewport') as HTMLElement | null
  if (!target) return false
  if (!viewport || !viewportReady(viewport)) return false

  const firstDay = viewport.querySelector('[id^="day-"]')
  const tableTaller = viewport.scrollHeight > viewport.clientHeight + 80
  if (firstDay && firstDay.id !== id && !tableTaller) return false


  const sticky = viewport.querySelector('thead') as HTMLElement | null
  const offsetY = (sticky?.getBoundingClientRect().height ?? 0) + 4
  const lessonCol = viewport.querySelector('tbody td') as HTMLElement | null
  const offsetX = (lessonCol?.getBoundingClientRect().width ?? 110) + 4
  const t = target.getBoundingClientRect()
  const v = viewport.getBoundingClientRect()
  if (align === 'start') {
    viewport.scrollTo({
      top: Math.max(0, viewport.scrollTop + (t.top - v.top) - offsetY),
      left: Math.max(0, viewport.scrollLeft + (t.left - v.left) - offsetX),
    })
  } else {
    const visibleTop = v.top + offsetY
    const visibleLeft = v.left + offsetX
    let dy = 0
    let dx = 0
    if (t.top < visibleTop) dy = t.top - visibleTop
    else if (t.bottom > v.bottom) dy = t.bottom - v.bottom
    if (t.left < visibleLeft) dx = t.left - visibleLeft
    else if (t.right > v.right) dx = t.right - v.right
    if (dx || dy) {
      viewport.scrollTo({
        top: Math.max(0, viewport.scrollTop + dy),
        left: Math.max(0, viewport.scrollLeft + dx),
      })
    }
  }

  if (align === 'start' && firstDay && firstDay.id !== id && tableTaller && viewport.scrollTop < 8) {
    return false
  }
  return true
}

function restorePixels(top: number, left: number) {
  const viewport = document.querySelector('.overlay-scroll-viewport') as HTMLElement | null
  if (!viewport || !viewportReady(viewport)) return false
  viewport.scrollTo({ top, left })
  if (top > 8 && viewport.scrollTop < 8) return false
  return true
}

export function SchedulePage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const storedTab = loadTab()
  const urlLevel = params.get('school_level')
  const level: SchoolLevel =
    urlLevel === 'secondary' || urlLevel === 'elementary'
      ? urlLevel
      : storedTab?.school_level === 'secondary'
        ? 'secondary'
        : 'elementary'
  const shiftRaw = params.get('shift_id')
  const shiftId =
    shiftRaw && Number(shiftRaw)
      ? Number(shiftRaw)
      : urlLevel
        ? null
        : storedTab?.shift_id ?? null
  const [toast, setToast] = useState<{ kind: 'success' | 'danger'; text: string } | null>(null)
  const { expanded, setExpanded } = useScheduleExpand()
  const [slot, setSlot] = useState<SlotKey | null>(null)
  const [whyCell, setWhyCell] = useState<CellOut | null>(null)
  const hashTimer = useRef<number>(0)
  const restoreDone = useRef(false)
  const syncAllowed = useRef(false)
  const pendingAnchor = useRef(bootAnchor)

  function finishRestore() {
    restoreDone.current = true
    syncAllowed.current = true
  }

  function tryRestoreAnchor() {
    if (restoreDone.current) return true
    const saved = loadSavedView(level, shiftId)
    const liveHash = window.location.hash.replace(/^#/, '')
    const hash = liveHash || saved?.hash || pendingAnchor.current || ''
    if (hash) {
      const align = hash.startsWith('slot-') ? 'nearest' : 'start'
      if (scrollScheduleAnchor(hash, align)) {
        replaceHash(hash)
        const viewport = document.querySelector('.overlay-scroll-viewport') as HTMLElement | null
        if (viewport) {
          saveSavedView(level, shiftId, {
            hash,
            top: viewport.scrollTop,
            left: viewport.scrollLeft,
          })
        }
        finishRestore()
        return true
      }
    }
    if (saved && (saved.top > 0 || saved.left > 0)) {
      if (restorePixels(saved.top, saved.left)) {
        if (saved.hash) replaceHash(saved.hash)
        finishRestore()
        return true
      }
    }
    if (!hash && (!saved || (saved.top === 0 && saved.left === 0))) {
      finishRestore()
      return true
    }
    return false
  }

  function setLevel(next: SchoolLevel) {
    restoreDone.current = false
    syncAllowed.current = false
    pendingAnchor.current = ''
    saveTab(next, null)
    const search = `?school_level=${next}`
    navigate(
      { pathname: '/schedule', search, hash: '' },
      { replace: true, preventScrollReset: true },
    )
  }

  function setShiftId(id: number) {
    restoreDone.current = false
    syncAllowed.current = false
    saveTab(level, id)
    const sp = new URLSearchParams()
    sp.set('school_level', level)
    sp.set('shift_id', String(id))
    const search = `?${sp.toString()}`
    navigate(
      { pathname: '/schedule', search, hash: window.location.hash },
      { replace: true, preventScrollReset: true },
    )
  }

  function stayAt(classId: number, day: number, lesson: number) {
    const id = slotAnchor(classId, day, lesson)
    replaceHash(id)
    requestAnimationFrame(() => {
      scrollScheduleAnchor(id, 'nearest')
      const viewport = document.querySelector('.overlay-scroll-viewport') as HTMLElement | null
      if (viewport) {
        saveSavedView(level, shiftId, {
          hash: id,
          top: viewport.scrollTop,
          left: viewport.scrollLeft,
        })
      }
    })
  }

  function syncHashFromScroll() {
    if (!syncAllowed.current) return
    const viewport = document.querySelector('.overlay-scroll-viewport') as HTMLElement | null
    if (!viewport) return
    const days = viewport.querySelectorAll<HTMLElement>('[id^="day-"]')
    if (!days.length) return
    const sticky = viewport.querySelector('thead') as HTMLElement | null
    const viewTop =
      viewport.getBoundingClientRect().top + (sticky?.getBoundingClientRect().height ?? 0) + 8
    let current = days[0].id
    days.forEach((el) => {
      if (el.getBoundingClientRect().top <= viewTop) current = el.id
    })
    saveSavedView(level, shiftId, {
      hash: current,
      top: viewport.scrollTop,
      left: viewport.scrollLeft,
    })
    window.clearTimeout(hashTimer.current)
    hashTimer.current = window.setTimeout(() => {
      if (window.location.hash !== `#${current}`) replaceHash(current)
    }, 50)
  }

  useEffect(() => {
    if (!toast) return
    const ms = toast.kind === 'danger' ? 10000 : 4000
    const t = setTimeout(() => setToast(null), ms)
    return () => clearTimeout(t)
  }, [toast])

  useEffect(() => {
    saveTab(level, shiftId)
    if (params.get('school_level')) return
    const sp = new URLSearchParams()
    sp.set('school_level', level)
    if (shiftId) sp.set('shift_id', String(shiftId))
    navigate(
      {
        pathname: '/schedule',
        search: `?${sp.toString()}`,
        hash: window.location.hash,
      },
      { replace: true, preventScrollReset: true },
    )
  }, [])

  const gridQ = useQuery({
    queryKey: ['schedule', 'grid', level, shiftId],
    queryFn: () => fetchGrid(level, shiftId),
  })

  const teacherHoverCss = useMemo(() => {
    const cells = gridQ.data?.cells ?? []
    const keys = [...new Set(cells.map(teacherHoverKey).filter(Boolean))]
    return buildTeacherHoverCss(keys)
  }, [gridQ.data])

  const addM = useMutation({
    mutationFn: async (p: {
      class_id: number
      day_of_week: number
      lesson_number: number
      assignment_id: number
      classroom_id: number | null
    }) => createScheduleCell(p),
    onSuccess: async (_cell, p) => {
      setSlot(null)
      setToast({ kind: 'success', text: 'Урок добавлен' })
      replaceHash(slotAnchor(p.class_id, p.day_of_week, p.lesson_number))
      await qc.invalidateQueries({ queryKey: ['schedule', 'grid'] })
      stayAt(p.class_id, p.day_of_week, p.lesson_number)
    },
  })

  const moveM = useMutation({
    mutationFn: async (p: {
      cell_id: number
      class_id: number
      day_of_week: number
      lesson_number: number
    }) =>
      updateScheduleCell(p.cell_id, {
        day_of_week: p.day_of_week,
        lesson_number: p.lesson_number,
        class_id: p.class_id,
      }),
    onSuccess: async (_cell, p) => {
      setToast({ kind: 'success', text: 'Урок перемещён' })
      replaceHash(slotAnchor(p.class_id, p.day_of_week, p.lesson_number))
      await qc.invalidateQueries({ queryKey: ['schedule', 'grid'] })
      stayAt(p.class_id, p.day_of_week, p.lesson_number)
    },
    onError: (e) => setToast({ kind: 'danger', text: extractApiError(e) }),
  })

  const delM = useMutation({
    mutationFn: (p: { cell_id: number; class_id: number; day: number; lesson: number }) =>
      deleteScheduleCell(p.cell_id),
    onSuccess: async (_ok, p) => {
      setToast({ kind: 'success', text: 'Урок удалён' })
      replaceHash(slotAnchor(p.class_id, p.day, p.lesson))
      await qc.invalidateQueries({ queryKey: ['schedule', 'grid'] })
      stayAt(p.class_id, p.day, p.lesson)
    },
    onError: (e) => setToast({ kind: 'danger', text: extractApiError(e) }),
  })

  useEffect(() => {
    restoreDone.current = false
    syncAllowed.current = false
  }, [level, shiftId])

  useEffect(() => {
    if (!gridQ.data?.classes.length) return
    let cancelled = false
    let tries = 0
    const run = () => {
      if (cancelled) return
      if (tryRestoreAnchor()) return
      if (tries++ > 60) {
        finishRestore()
        return
      }
      window.setTimeout(run, 50)
    }
    run()
    return () => {
      cancelled = true
    }
  }, [gridQ.data, level, shiftId])

  if (gridQ.isPending && !gridQ.data) return <p>Загрузка…</p>
  if (gridQ.isError) return <p className="text-danger">{extractApiError(gridQ.error)}</p>

  const grid = gridQ.data!

  const cellsBySlot = new Map<string, CellOut[]>()
  for (const c of grid.cells) {
    const key = `${c.class_id}:${c.day_of_week}:${c.lesson_number}`
    const arr = cellsBySlot.get(key) ?? []
    arr.push(c)
    cellsBySlot.set(key, arr)
  }

  function onDragStartCell(e: React.DragEvent, cell: CellOut) {
    e.dataTransfer.setData('text/cell-id', String(cell.id))
    e.dataTransfer.effectAllowed = 'move'
  }

  function onDropSlot(
    e: React.DragEvent,
    target: { class_id: number; day: number; lesson: number },
  ) {
    e.preventDefault()
    const raw = e.dataTransfer.getData('text/cell-id')
    if (!raw) return
    const cell_id = Number(raw)
    if (!cell_id) return
    moveM.mutate({
      cell_id,
      class_id: target.class_id,
      day_of_week: target.day,
      lesson_number: target.lesson,
    })
  }

  const rows: Array<
    | { kind: 'day'; day: number }
    | { kind: 'class_hour'; day: number }
    | { kind: 'lesson'; day: number; lesson: number }
  > = []
  for (let day = 1; day <= grid.working_days; day++) {
    rows.push({ kind: 'day', day })
    if (
      grid.current_shift &&
      grid.current_shift.class_hour_day === day &&
      grid.class_hour_time_label
    ) {
      rows.push({ kind: 'class_hour', day })
    }
    for (const lesson of grid.lessons_range) {
      rows.push({ kind: 'lesson', day, lesson })
    }
  }

  return (
    <div className={`schedule-grid-page${expanded ? ' is-expanded' : ''}`}>
      {toast && (
        <div
          className={`alert alert-${toast.kind} alert-dismissible fade show schedule-toast py-2 mb-0`}
          role="alert"
          style={{ whiteSpace: 'pre-line' }}
        >
          {toast.kind === 'danger' && <strong className="d-block">Нельзя изменить расписание</strong>}
          {toast.text}
          <button
            type="button"
            className="btn-close"
            aria-label="Закрыть"
            onClick={() => setToast(null)}
          />
        </div>
      )}

      <div className="schedule-grid-chrome">
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

        <div className="schedule-grid-meta d-flex gap-3 align-items-center mb-3 flex-wrap">
          {grid.settings && (
            <span className="badge schedule-meta-badge">
              Режим:{' '}
              {grid.settings.classroom_mode === 'class_room'
                ? 'учитель приходит к классу'
                : 'дети приходят к учителю'}
            </span>
          )}
          {grid.classroom_warnings.length > 0 && (
            <span
              className="badge schedule-warn-badge"
              title={grid.classroom_warnings.map((w) => w.message).join('; ')}
            >
              {grid.classroom_warnings.length} без кабинета
            </span>
          )}
        </div>

        {grid.shifts.length > 0 && (
          <ul className="nav nav-pills mb-3">
            {grid.shifts.map((s) => (
              <li className="nav-item" key={s.id}>
                <button
                  type="button"
                  className={`nav-link ${grid.current_shift_id === s.id ? 'active' : ''}`}
                  onClick={() => setShiftId(s.id)}
                >
                  {s.name}
                </button>
              </li>
            ))}
          </ul>
        )}

        {expanded && (
          <button
            type="button"
            className="btn btn-dark btn-sm schedule-expand-btn ms-auto"
            title="Свернуть таблицу"
            aria-label="Свернуть таблицу"
            onClick={() => setExpanded(false)}
          >
            <i className="bi bi-arrows-angle-contract" />
            <span className="ms-1">Свернуть</span>
          </button>
        )}
      </div>

      {grid.classes.length === 0 ? (
        <div className="card">
          <div className="card-body text-muted text-center py-5">
            Нет классов для отображения. Привяжите классы к смене.
          </div>
        </div>
      ) : (
        <div className="card schedule-grid-card">
          {teacherHoverCss ? <style>{teacherHoverCss}</style> : null}
          <OverlayScrollArea
            key={`${level}-${shiftId ?? 'auto'}`}
            onScroll={syncHashFromScroll}
            onViewportReady={() => {
              tryRestoreAnchor()
            }}
          >
            <table
              className="table table-bordered mb-0 schedule-grid-table"
              onMouseOver={(e) => {
                const card = (e.target as HTMLElement).closest('.lesson-card') as HTMLElement | null
                const key = card?.dataset.teacherKey || ''
                applyTeacherHover(e.currentTarget, key || null)
              }}
              onMouseOut={(e) => {
                const table = e.currentTarget
                const rel = e.relatedTarget
                const next =
                  rel instanceof Element ? (rel.closest('.lesson-card') as HTMLElement | null) : null
                if (next && table.contains(next)) {
                  applyTeacherHover(table, next.dataset.teacherKey || null)
                  return
                }
                applyTeacherHover(table, null)
              }}
            >
              <thead className="table-light">
                <tr>
                  <th className="schedule-slot-index">Урок</th>
                  {grid.classes.map((c) => (
                    <th key={c.id} id={classAnchor(c.id)} className="text-center">
                      {c.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => {
                  if (row.kind === 'day') {
                    return (
                      <tr key={`d-${row.day}`} id={dayAnchor(row.day)}>
                        <td
                          colSpan={grid.classes.length + 1}
                          className="bg-light fw-semibold py-1"
                          style={{ textAlign: 'center' }}
                        >
                          {grid.day_names[row.day - 1]}
                        </td>
                      </tr>
                    )
                  }
                  const lesson = row.kind === 'class_hour' ? 0 : row.lesson
                  const time =
                    row.kind === 'class_hour'
                      ? grid.class_hour_time_label
                      : grid.lesson_times_by_day[row.day]?.[lesson]
                  return (
                    <tr key={`r-${idx}`}>
                      <td className="schedule-slot-index text-center align-middle">
                        <div className="schedule-slot-num">
                          {row.kind === 'class_hour' ? 'Классный час' : lesson}
                        </div>
                        {time ? <BellLabel time={time} /> : null}
                      </td>
                      {grid.classes.map((c) => {
                        const key = `${c.id}:${row.day}:${lesson}`
                        const cells = cellsBySlot.get(key) ?? []
                        return (
                          <td
                            key={c.id}
                            id={slotAnchor(c.id, row.day, lesson)}
                            className="p-1 align-top"
                            style={{ minWidth: 130, cursor: cells.length === 0 ? 'pointer' : 'default' }}
                            onDragOver={(e) => e.preventDefault()}
                            onDrop={(e) =>
                              onDropSlot(e, {
                                class_id: c.id,
                                day: row.day,
                                lesson,
                              })
                            }
                            onClick={(e) => {
                              if (cells.length > 0) return
                              if ((e.target as HTMLElement).closest('button')) return
                              setSlot({
                                class_id: c.id,
                                day: row.day,
                                lesson,
                                class_name: c.name,
                              })
                            }}
                          >
                            {cells.length === 0 ? (
                              <div className="text-muted text-center small py-2">+</div>
                            ) : (
                              cells.map((cell, i) => (
                                <div
                                  key={cell.id}
                                  draggable
                                  data-teacher-key={teacherHoverKey(cell) || undefined}
                                  onDragStart={(e) => {
                                    applyTeacherHover(
                                      e.currentTarget.closest('.schedule-grid-table'),
                                      null,
                                    )
                                    onDragStartCell(e, cell)
                                  }}
                                  className="lesson-card rounded mb-1 position-relative"
                                  style={{
                                    ['--lesson-color' as string]: cell.subject_color,
                                  }}
                                >
                                  {i > 0 && <hr className="my-1" />}
                                  <div className="fw-semibold lesson-subject">
                                    {cell.subject_name}
                                    {cell.group_number != null && (
                                      <span className="badge schedule-group-badge ms-1">
                                        гр.{cell.group_number}
                                      </span>
                                    )}
                                  </div>
                                  <div className="small teacher-name">{cell.teacher_name ?? '?'}</div>
                                  {cell.classroom_name && (
                                    <div className="small text-muted">каб. {cell.classroom_name}</div>
                                  )}
                                  <div className="lesson-card-actions">
                                    <button
                                      type="button"
                                      className="lesson-card-action"
                                      title="Почему этот слот"
                                      onPointerDown={suppressCardDrag}
                                      onClick={(ev) => {
                                        ev.stopPropagation()
                                        setWhyCell(cell)
                                      }}
                                    >
                                      ?
                                    </button>
                                    <button
                                      type="button"
                                      className="lesson-card-action is-danger"
                                      title="Удалить"
                                      onPointerDown={suppressCardDrag}
                                      onClick={(ev) => {
                                        ev.stopPropagation()
                                        if (confirm('Удалить урок?'))
                                          delM.mutate({
                                            cell_id: cell.id,
                                            class_id: cell.class_id,
                                            day: cell.day_of_week,
                                            lesson: cell.lesson_number,
                                          })
                                      }}
                                    >
                                      ×
                                    </button>
                                  </div>
                                </div>
                              ))
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </OverlayScrollArea>
        </div>
      )}

      {slot && (
        <AddLessonModal
          slot={slot}
          dayNames={grid.day_names}
          error={addM.isError ? extractApiError(addM.error) : null}
          onClose={() => {
            addM.reset()
            setSlot(null)
          }}
          onSubmit={(assignment_id, classroom_id) =>
            addM.mutate({
              class_id: slot.class_id,
              day_of_week: slot.day,
              lesson_number: slot.lesson,
              assignment_id,
              classroom_id,
            })
          }
          submitting={addM.isPending}
        />
      )}

      {whyCell && (
        <WhyCellModal cell={whyCell} onClose={() => setWhyCell(null)} />
      )}
    </div>
  )
}

function AddLessonModal(props: {
  slot: SlotKey
  dayNames: string[]
  error: string | null
  onClose: () => void
  onSubmit: (assignment_id: number, classroom_id: number | null) => void
  submitting: boolean
}) {
  const { slot, dayNames, error, onClose, onSubmit, submitting } = props
  const [subjectName, setSubjectName] = useState<string>('')
  const [assignmentId, setAssignmentId] = useState<number | ''>('')
  const [classroomId, setClassroomId] = useState<number | ''>('')

  const q = useQuery({
    queryKey: ['schedule', 'assignments-for-class', slot.class_id],
    queryFn: () => fetchAssignmentsForClass(slot.class_id),
  })

  const subjects = useMemo(() => {
    if (!q.data) return [] as { name: string; color: string }[]
    const m = new Map<string, string>()
    for (const a of q.data.assignments) {
      if (!m.has(a.subject_name)) m.set(a.subject_name, a.subject_color)
    }
    return [...m.entries()].map(([name, color]) => ({ name, color }))
  }, [q.data])

  const filteredAssignments = useMemo(
    () => q.data?.assignments.filter((a) => a.subject_name === subjectName) ?? [],
    [q.data, subjectName],
  )

  useEffect(() => {
    if (filteredAssignments.length === 1) {
      const only = filteredAssignments[0]
      setAssignmentId(only.id)
      if (only.preferred_classroom_id) setClassroomId(only.preferred_classroom_id)
    } else {
      setAssignmentId('')
    }
  }, [filteredAssignments])

  const slotLabel = slot.lesson === 0 ? 'классный час' : `урок ${slot.lesson}`
  const title = `${slot.class_name}, ${dayNames[slot.day - 1]}, ${slotLabel}`

  return (
    <ModalPortal>
    <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,.35)' }}>
      <div className="modal-dialog">
        <div className="modal-content">
          <div className="modal-header">
            <h5 className="modal-title">Добавить урок</h5>
            <button type="button" className="btn-close" aria-label="Закрыть" onClick={onClose} />
          </div>
          <div className="modal-body">
            <div className="text-muted small mb-2">{title}</div>
            {error && (
              <div className="alert alert-danger py-2" style={{ whiteSpace: 'pre-line' }}>
                <strong>Нельзя добавить урок</strong>
                <div className="mt-1">{error}</div>
              </div>
            )}
            {q.isLoading && <div>Загрузка…</div>}
            {q.isError && (
              <div className="text-danger">{(q.error as Error).message}</div>
            )}
            {q.data && q.data.assignments.length === 0 && (
              <div className="text-muted">Все часы для этого класса распределены.</div>
            )}
            {q.data && q.data.assignments.length > 0 && (
              <>
                <div className="mb-3">
                  <label className="form-label fw-bold">Предмет</label>
                  <select
                    className="form-select"
                    value={subjectName}
                    onChange={(e) => setSubjectName(e.target.value)}
                  >
                    <option value="">Выберите предмет…</option>
                    {subjects.map((s) => (
                      <option key={s.name} value={s.name}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="mb-3">
                  <label className="form-label fw-bold">Учитель</label>
                  <select
                    className="form-select"
                    value={assignmentId === '' ? '' : String(assignmentId)}
                    disabled={!subjectName}
                    onChange={(e) => {
                      const id = e.target.value === '' ? '' : Number(e.target.value)
                      setAssignmentId(id)
                      const picked = filteredAssignments.find((a) => a.id === id)
                      if (picked?.preferred_classroom_id) {
                        setClassroomId(picked.preferred_classroom_id)
                      }
                    }}
                  >
                    <option value="">
                      {subjectName ? 'Выберите учителя…' : 'Сначала выберите предмет'}
                    </option>
                    {filteredAssignments.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.teacher_name ?? '?'}
                        {a.group_number != null ? ` (гр.${a.group_number})` : ''}
                        {` — ${a.remaining_hours} ч.`}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="mb-3">
                  <label className="form-label fw-bold">Кабинет</label>
                  <select
                    className="form-select"
                    value={classroomId === '' ? '' : String(classroomId)}
                    onChange={(e) =>
                      setClassroomId(e.target.value === '' ? '' : Number(e.target.value))
                    }
                  >
                    <option value="">Без кабинета</option>
                    {q.data.classrooms.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.display_name}
                      </option>
                    ))}
                  </select>
                </div>
                {assignmentId !== '' && (
                  <WhyPanel
                    assignmentId={assignmentId}
                    day={slot.day}
                    lesson={slot.lesson}
                    classroomId={classroomId === '' ? null : classroomId}
                  />
                )}
              </>
            )}
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Отмена
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={assignmentId === '' || submitting}
              onClick={() => {
                if (assignmentId === '') return
                onSubmit(assignmentId, classroomId === '' ? null : classroomId)
              }}
            >
              {submitting ? 'Сохранение…' : 'Добавить'}
            </button>
          </div>
        </div>
      </div>
    </div>
    </ModalPortal>
  )
}

function WhyPanel(props: {
  assignmentId: number
  day: number
  lesson: number
  classroomId: number | null
  cellId?: number | null
}) {
  const { assignmentId, day, lesson, classroomId, cellId } = props
  const q = useQuery({
    queryKey: ['schedule', 'explain', assignmentId, day, lesson, classroomId, cellId ?? null],
    queryFn: () =>
      explainSlot({
        assignment_id: assignmentId,
        day_of_week: day,
        lesson_number: lesson,
        classroom_id: classroomId,
        cell_id: cellId ?? null,
      }),
  })
  return (
    <div className="border rounded p-2 bg-light small">
      <div className="fw-semibold mb-1">Почему</div>
      {q.isLoading && <div className="text-muted">Проверяем слот…</div>}
      {q.isError && <div className="text-danger">{(q.error as Error).message}</div>}
      {q.data && (
        <>
          <div className={q.data.allowed ? 'text-success' : 'text-danger'} style={{ whiteSpace: 'pre-line' }}>
            {q.data.text}
          </div>
          {q.data.llm_used && (
            <div className="text-muted mt-1">Текст сформулирован Qwen по фактам валидатора.</div>
          )}
          {q.data.alternatives.length > 0 && (
            <div className="mt-2">
              <div className="text-muted">Другие свободные слоты:</div>
              <ul className="mb-0 mt-1 ps-3">
                {q.data.alternatives.map((a) => (
                  <li key={`${a.day_of_week}-${a.lesson_number}`}>{a.label}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function WhyCellModal(props: { cell: CellOut; onClose: () => void }) {
  const { cell, onClose } = props
  return (
    <ModalPortal>
      <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,.35)' }}>
        <div className="modal-dialog">
          <div className="modal-content">
            <div className="modal-header">
              <h5 className="modal-title">Почему этот слот</h5>
              <button type="button" className="btn-close" aria-label="Закрыть" onClick={onClose} />
            </div>
            <div className="modal-body">
              <div className="text-muted small mb-2">
                {cell.subject_name}
                {cell.teacher_name ? ` · ${cell.teacher_name}` : ''}
              </div>
              <WhyPanel
                assignmentId={cell.assignment_id}
                day={cell.day_of_week}
                lesson={cell.lesson_number}
                classroomId={cell.classroom_id}
                cellId={cell.id}
              />
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                Закрыть
              </button>
            </div>
          </div>
        </div>
      </div>
    </ModalPortal>
  )
}
