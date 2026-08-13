import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { OverlayScrollArea } from '../components/OverlayScrollArea'
import { extractApiError, apiJson } from '../api/client'
import { useScheduleExpand } from '../layouts/ScheduleLayout'

type SchoolLevel = 'elementary' | 'secondary'

type ShiftBrief = {
  id: number
  name: string
  school_level: string
  working_days: number
  max_lessons_per_day: number
  start_lesson: number
  lessons_count: number
  class_hour_day: number | null
  class_hour_time_label: string | null
}

type SchoolClassRow = {
  id: number
  name: string
  grade: number
  school_level: string
  shift_id: number | null
}

type ScheduleSettings = {
  school_level: string
  max_lessons_per_subject_per_day: number
  classroom_mode: 'class_room' | 'teacher_room'
  elementary_group_subjects_leave: boolean
}

type ClassroomWarning = { type: string; message: string }

type CellOut = {
  id: number
  class_id: number
  day_of_week: number
  lesson_number: number
  assignment_id: number
  classroom_id: number | null
  subject_id: number
  subject_name: string
  subject_color: string
  teacher_id: number | null
  teacher_name: string | null
  group_number: number | null
  classroom_name: string | null
}

type GridData = {
  school_level: SchoolLevel
  current_shift_id: number | null
  current_shift: ShiftBrief | null
  shifts: ShiftBrief[]
  classes: SchoolClassRow[]
  day_names: string[]
  working_days: number
  max_lessons: number
  lessons_range: number[]
  lesson_times_by_day: Record<number, Record<number, string>>
  class_hour_time_label: string
  cells: CellOut[]
  classroom_warnings: ClassroomWarning[]
  settings: ScheduleSettings | null
}

type AssignmentChoice = {
  id: number
  subject_id: number
  subject_name: string
  subject_color: string
  teacher_id: number | null
  teacher_name: string | null
  group_number: number | null
  remaining_hours: number
  preferred_classroom_id: number | null
}

type ClassroomChoice = {
  id: number
  number: string
  name: string | null
  display_name: string
}

type AssignmentsData = {
  assignments: AssignmentChoice[]
  classrooms: ClassroomChoice[]
}

type SlotKey = { class_id: number; day: number; lesson: number; class_name: string }

if (typeof window !== 'undefined') {
  try {
    window.history.scrollRestoration = 'manual'
  } catch {
    /* ignore */
  }
}

const bootAnchor = typeof window !== 'undefined' ? window.location.hash.replace(/^#/, '') : ''

function dbg(
  location: string,
  message: string,
  data: Record<string, unknown>,
  hypothesisId: string,
) {
  // #region agent log
  fetch('http://127.0.0.1:7749/ingest/55d6f9a3-7152-4cf5-827c-1203474325d2', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '1126ac' },
    body: JSON.stringify({
      sessionId: '1126ac',
      runId: 'pre-fix',
      hypothesisId,
      location,
      message,
      data,
      timestamp: Date.now(),
    }),
  }).catch(() => {})
  // #endregion
}

function dbg911(
  location: string,
  message: string,
  data: Record<string, unknown>,
  hypothesisId: string,
) {
  // #region agent log
  fetch('http://127.0.0.1:7749/ingest/55d6f9a3-7152-4cf5-827c-1203474325d2', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '911585' },
    body: JSON.stringify({
      sessionId: '911585',
      runId: 'pre-fix',
      hypothesisId,
      location,
      message,
      data,
      timestamp: Date.now(),
    }),
  }).catch(() => {})
  // #endregion
}

function elBox(el: Element | null) {
  if (!el) return null
  const r = el.getBoundingClientRect()
  const cs = getComputedStyle(el)
  return {
    w: Math.round(r.width),
    h: Math.round(r.height),
    t: Math.round(r.top),
    l: Math.round(r.left),
    b: Math.round(r.bottom),
    rgt: Math.round(r.right),
    display: cs.display,
    visibility: cs.visibility,
    opacity: cs.opacity,
    z: cs.zIndex,
  }
}

if (typeof window !== 'undefined') {
  // #region agent log
  dbg(
    'SchedulePage.tsx:boot',
    'module boot hash',
    {
      bootAnchor,
      href: window.location.href,
      search: window.location.search,
      hash: window.location.hash,
    },
    'A',
  )
  // #endregion
}

function dayAnchor(day: number) {
  return `day-${day}`
}

function slotAnchor(classId: number, day: number, lesson: number) {
  return `slot-${classId}-${day}-${lesson}`
}

function classAnchor(classId: number) {
  return `class-${classId}`
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
  const metrics = viewport
    ? {
        ch: viewport.clientHeight,
        sh: viewport.scrollHeight,
        st: viewport.scrollTop,
        ready: viewportReady(viewport),
        taller: viewport.scrollHeight > viewport.clientHeight + 80,
      }
    : null
  if (!target) {
    // #region agent log
    dbg('SchedulePage.tsx:scrollScheduleAnchor', 'no target', { id, metrics }, 'B')
    // #endregion
    return false
  }
  if (!viewport || !viewportReady(viewport)) {
    // #region agent log
    dbg('SchedulePage.tsx:scrollScheduleAnchor', 'viewport not ready', { id, metrics }, 'B')
    // #endregion
    return false
  }

  const firstDay = viewport.querySelector('[id^="day-"]')
  const tableTaller = viewport.scrollHeight > viewport.clientHeight + 80
  if (firstDay && firstDay.id !== id && !tableTaller) {
    // #region agent log
    dbg(
      'SchedulePage.tsx:scrollScheduleAnchor',
      'table not taller',
      { id, firstDay: firstDay.id, metrics },
      'B',
    )
    // #endregion
    return false
  }

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
    // #region agent log
    dbg(
      'SchedulePage.tsx:scrollScheduleAnchor',
      'scrollTop still ~0 after scrollTo',
      { id, align, scrollTop: viewport.scrollTop, metrics },
      'C',
    )
    // #endregion
    return false
  }
  // #region agent log
  dbg(
    'SchedulePage.tsx:scrollScheduleAnchor',
    'scroll ok',
    { id, align, scrollTop: viewport.scrollTop, ch: viewport.clientHeight, sh: viewport.scrollHeight },
    'C',
  )
  // #endregion
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
  const [hoveredTeacherId, setHoveredTeacherId] = useState<number | null>(null)
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
    // #region agent log
    dbg(
      'SchedulePage.tsx:tryRestoreAnchor',
      'attempt',
      {
        level,
        shiftId,
        storageKey: viewStorageKey(level, shiftId),
        liveHash,
        boot: pendingAnchor.current,
        saved,
        hash,
        href: window.location.href,
      },
      'A',
    )
    // #endregion
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
      // #region agent log
      dbg(
        'SchedulePage.tsx:tryRestoreAnchor',
        'nothing to restore, finish',
        { liveHash, boot: pendingAnchor.current, saved, shiftId, level },
        'A',
      )
      // #endregion
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
    // #region agent log
    dbg(
      'SchedulePage.tsx:setLevel',
      'navigate level',
      { next, search, href: window.location.href },
      'A',
    )
    // #endregion
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
    // #region agent log
    dbg(
      'SchedulePage.tsx:setShiftId',
      'navigate shift',
      { id, level, search, href: window.location.href },
      'A',
    )
    // #endregion
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
    // #region agent log
    dbg(
      'SchedulePage.tsx:syncHashFromScroll',
      'sync from scroll',
      {
        current,
        prevHash: window.location.hash,
        scrollTop: viewport.scrollTop,
        syncAllowed: syncAllowed.current,
      },
      'D',
    )
    // #endregion
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

  useLayoutEffect(() => {
    const expandBtn = document.querySelector('.schedule-expand-btn')
    const header = document.querySelector('.page-header')
    const actions = document.querySelector('.schedule-grid-actions')
    const page = document.querySelector('.schedule-grid-page')
    const inView = (box: ReturnType<typeof elBox>) => {
      if (!box) return false
      return box.w > 0 && box.h > 0 && box.b > 0 && box.t < window.innerHeight && box.rgt > 0 && box.l < window.innerWidth
    }
    const expandBox = elBox(expandBtn)
    const headerBox = elBox(header)
    const actionsBox = elBox(actions)
    // #region agent log
    dbg911(
      'SchedulePage.tsx:layout',
      'button geometry',
      {
        expanded,
        stored: sessionStorage.getItem('schedule:expanded'),
        bodyExpanded: document.body.classList.contains('schedule-grid-expanded'),
        pageClass: page?.className ?? null,
        href: window.location.href,
        expandInDom: !!expandBtn,
        expandParent: expandBtn?.parentElement?.className ?? null,
        expandBox,
        headerBox,
        actionsBox,
        expandVisible: inView(expandBox),
        headerVisible: inView(headerBox),
        chromeH: document.querySelector('.schedule-grid-chrome')?.getBoundingClientRect().height ?? null,
        pageH: page?.getBoundingClientRect().height ?? null,
        vw: window.innerWidth,
        vh: window.innerHeight,
      },
      'A-B-D-E',
    )
    // #endregion
  }, [expanded])

  useEffect(() => {
    // #region agent log
    dbg(
      'SchedulePage.tsx:mount',
      'resolved tab',
      {
        level,
        shiftId,
        urlLevel: params.get('school_level'),
        urlShift: params.get('shift_id'),
        href: window.location.href,
        stored: loadTab(),
      },
      'A',
    )
    // #endregion
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
    queryFn: () =>
      apiJson<GridData>(
        `/api/schedule/grid?school_level=${level}${shiftId ? `&shift_id=${shiftId}` : ''}`,
      ),
  })

  const addM = useMutation({
    mutationFn: async (p: {
      class_id: number
      day_of_week: number
      lesson_number: number
      assignment_id: number
      classroom_id: number | null
    }) => apiJson<CellOut>('/api/schedule/cells', { method: 'POST', body: JSON.stringify(p) }),
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
      apiJson<CellOut>(`/api/schedule/cells/${p.cell_id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          day_of_week: p.day_of_week,
          lesson_number: p.lesson_number,
          class_id: p.class_id,
        }),
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
      apiJson<void>(`/api/schedule/cells/${p.cell_id}`, { method: 'DELETE' }),
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
        // #region agent log
        dbg(
          'SchedulePage.tsx:restoreEffect',
          'gave up after retries',
          { tries, href: window.location.href, hash: window.location.hash },
          'B',
        )
        // #endregion
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

  // #region agent log
  dbg911(
    'SchedulePage.tsx:render',
    'render path',
    {
      expanded,
      stored: sessionStorage.getItem('schedule:expanded'),
      bodyExpanded:
        typeof document !== 'undefined' &&
        document.body.classList.contains('schedule-grid-expanded'),
      pending: gridQ.isPending && !gridQ.data,
      error: gridQ.isError,
      hasData: !!gridQ.data,
      classCount: gridQ.data?.classes.length ?? null,
    },
    'A-C-E',
  )
  // #endregion

  if (gridQ.isPending && !gridQ.data) return <p>Загрузка…</p>
  if (gridQ.isError) return <p className="text-danger">{(gridQ.error as Error).message}</p>

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
      {!expanded && (
        <div className="schedule-grid-actions d-flex justify-content-end align-items-center mb-2 gap-2">
          <span className="text-muted small">Drag&drop карточек переносит урок.</span>
        </div>
      )}

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
            <span className="badge bg-light text-dark border">
              Режим:{' '}
              {grid.settings.classroom_mode === 'class_room'
                ? 'учитель приходит к классу'
                : 'дети приходят к учителю'}
            </span>
          )}
          {grid.classroom_warnings.length > 0 && (
            <span
              className="badge bg-warning text-dark"
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
          <OverlayScrollArea
            key={`${level}-${shiftId ?? 'auto'}`}
            onScroll={syncHashFromScroll}
            onViewportReady={(el) => {
              // #region agent log
              dbg(
                'SchedulePage.tsx:onViewportReady',
                'viewport ready',
                {
                  ch: el.clientHeight,
                  sh: el.scrollHeight,
                  st: el.scrollTop,
                  restoreDone: restoreDone.current,
                },
                'E',
              )
              // #endregion
              tryRestoreAnchor()
            }}
          >
            <table
              className={`table table-bordered mb-0 schedule-grid-table${
                hoveredTeacherId != null ? ' is-teacher-hover' : ''
              }`}
            >
              <thead className="table-light">
                <tr>
                  <th style={{ width: 110 }}>Урок</th>
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
                      <td className="text-center align-middle">
                        <div className="fw-bold">
                          {row.kind === 'class_hour' ? 'Классный час' : lesson}
                        </div>
                        {time && (
                          <div className="small text-muted text-nowrap">{time}</div>
                        )}
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
                                  onDragStart={(e) => {
                                    setHoveredTeacherId(null)
                                    onDragStartCell(e, cell)
                                  }}
                                  className={`lesson-card border rounded p-1 mb-1 position-relative${
                                    hoveredTeacherId != null && cell.teacher_id === hoveredTeacherId
                                      ? ' teacher-highlight'
                                      : ''
                                  }`}
                                  style={{
                                    background: 'white',
                                    borderColor: cell.subject_color,
                                    borderWidth: 2,
                                    borderStyle: 'solid',
                                  }}
                                  onMouseEnter={() => {
                                    if (cell.teacher_id != null) setHoveredTeacherId(cell.teacher_id)
                                  }}
                                  onMouseLeave={() => setHoveredTeacherId(null)}
                                >
                                  {i > 0 && <hr className="my-1" />}
                                  <div className="fw-semibold" style={{ color: cell.subject_color }}>
                                    {cell.subject_name}
                                    {cell.group_number != null && (
                                      <span className="badge bg-warning text-dark ms-1">
                                        гр.{cell.group_number}
                                      </span>
                                    )}
                                  </div>
                                  <div className="small teacher-name">{cell.teacher_name ?? '?'}</div>
                                  {cell.classroom_name && (
                                    <div className="small text-muted">каб. {cell.classroom_name}</div>
                                  )}
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-link text-danger p-0 position-absolute"
                                    style={{ top: 2, right: 4 }}
                                    title="Удалить"
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
    queryFn: () =>
      apiJson<AssignmentsData>(`/api/schedule/assignments-for-class/${slot.class_id}`),
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
  )
}
