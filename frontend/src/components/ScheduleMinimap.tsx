import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from 'react'
import type { ScheduleCell as CellOut, SchoolClassRow } from '../api/schedule'

export type MinimapRow =
  | { kind: 'day'; day: number }
  | { kind: 'class_hour'; day: number }
  | { kind: 'lesson'; day: number; lesson: number }

const STORAGE_KEY = 'schedule:minimap'
const MAX_W = 228
const MAX_H = 172
const MIN_W = 148

type View = { sl: number; st: number; sw: number; sh: number; cw: number; ch: number }
type Weights = { cols: number[]; rows: number[] }
type Drag =
  | {
      startX: number
      startY: number
      startSl: number
      startSt: number
      mapW: number
      mapH: number
      moved: boolean
      slotId: string | null
    }
  | null

function loadOpen() {
  try {
    return localStorage.getItem(STORAGE_KEY) !== '0'
  } catch {
    return true
  }
}

function saveOpen(open: boolean) {
  try {
    localStorage.setItem(STORAGE_KEY, open ? '1' : '0')
  } catch {
    /* ignore */
  }
}

function teacherHoverKey(cell: Pick<CellOut, 'teacher_id' | 'teacher_name'>) {
  if (cell.teacher_id != null) return `id-${cell.teacher_id}`
  const name = (cell.teacher_name ?? '').trim()
  return name ? `name-${name}` : ''
}

function slotAnchor(classId: number, day: number, lesson: number) {
  return `slot-${classId}-${day}-${lesson}`
}

function emptyView(): View {
  return { sl: 0, st: 0, sw: 1, sh: 1, cw: 1, ch: 1 }
}

function readView(el: HTMLElement): View {
  return {
    sl: el.scrollLeft,
    st: el.scrollTop,
    sw: Math.max(1, el.scrollWidth),
    sh: Math.max(1, el.scrollHeight),
    cw: Math.max(1, el.clientWidth),
    ch: Math.max(1, el.clientHeight),
  }
}

function findViewport(from: HTMLElement | null) {
  return from?.closest('.schedule-grid-card')?.querySelector('.overlay-scroll-viewport') as
    | HTMLElement
    | null
}

function findTable(from: HTMLElement | null) {
  return from?.closest('.schedule-grid-card')?.querySelector('.schedule-grid-table') as
    | HTMLTableElement
    | null
}

function sizeFor(sw: number, sh: number) {
  const aspect = sw > 0 && sh > 0 ? sw / sh : 16 / 10
  let w = MAX_W
  let h = w / aspect
  if (h > MAX_H) {
    h = MAX_H
    w = h * aspect
  }
  if (w < MIN_W) {
    w = MIN_W
    h = Math.min(MAX_H, Math.max(100, w / aspect))
  }
  return { w: Math.round(w), h: Math.round(h) }
}

function clampScroll(el: HTMLElement, left: number, top: number) {
  el.scrollLeft = Math.max(0, Math.min(left, el.scrollWidth - el.clientWidth))
  el.scrollTop = Math.max(0, Math.min(top, el.scrollHeight - el.clientHeight))
}

function lessonTitle(cell: CellOut) {
  const bits = [cell.subject_name]
  if (cell.group_number != null) bits.push(`гр.${cell.group_number}`)
  if (cell.teacher_name) bits.push(cell.teacher_name)
  return bits.join(' · ')
}

export function ScheduleMinimap(props: {
  classes: SchoolClassRow[]
  rows: MinimapRow[]
  cellsBySlot: Map<string, CellOut[]>
  dayNames: string[]
  layoutKey: string
  onNavigateSlot: (id: string) => void
}) {
  const { classes, rows, cellsBySlot, dayNames, layoutKey, onNavigateSlot } = props
  const rootRef = useRef<HTMLElement>(null)
  const mapRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<Drag>(null)
  const [open, setOpen] = useState(loadOpen)
  const [view, setView] = useState<View>(emptyView)
  const [weights, setWeights] = useState<Weights | null>(null)

  const measure = useCallback(() => {
    const viewport = findViewport(rootRef.current)
    const table = findTable(rootRef.current)
    if (viewport) setView(readView(viewport))
    if (!table?.rows.length) return
    const head = table.rows[0]
    const cols = [...head.cells].map((c) => Math.max(1, c.getBoundingClientRect().width))
    const rowHs = [...table.rows].map((r) => Math.max(1, r.getBoundingClientRect().height))
    if (cols.length && rowHs.length) setWeights({ cols, rows: rowHs })
  }, [])

  useLayoutEffect(() => {
    if (!open) return
    const viewport = findViewport(rootRef.current)
    const table = findTable(rootRef.current)
    if (!viewport) return
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(viewport)
    if (table) ro.observe(table)
    viewport.addEventListener('scroll', measure, { passive: true })
    window.addEventListener('resize', measure)
    return () => {
      ro.disconnect()
      viewport.removeEventListener('scroll', measure)
      window.removeEventListener('resize', measure)
    }
  }, [open, measure, layoutKey])

  function toggle() {
    const next = !open
    setOpen(next)
    saveOpen(next)
  }

  function onWheel(e: ReactWheelEvent<HTMLDivElement>) {
    const viewport = findViewport(rootRef.current)
    if (!viewport) return
    viewport.scrollTop += e.deltaY
    viewport.scrollLeft += e.deltaX
    e.preventDefault()
  }

  function onPointerDown(e: ReactPointerEvent<HTMLDivElement>) {
    if (e.button !== 0) return
    const map = mapRef.current
    const viewport = findViewport(rootRef.current)
    if (!map || !viewport) return
    e.preventDefault()
    e.stopPropagation()
    map.setPointerCapture(e.pointerId)

    const mapRect = map.getBoundingClientRect()
    const localX = e.clientX - mapRect.left
    const localY = e.clientY - mapRect.top
    const v = readView(viewport)
    const viewLeft = (v.sl / v.sw) * mapRect.width
    const viewTop = (v.st / v.sh) * mapRect.height
    const viewW = (v.cw / v.sw) * mapRect.width
    const viewH = (v.ch / v.sh) * mapRect.height
    const insideView =
      localX >= viewLeft &&
      localX <= viewLeft + viewW &&
      localY >= viewTop &&
      localY <= viewTop + viewH

    const hit = (e.target as HTMLElement).closest('[data-slot-id]') as HTMLElement | null
    const slotId = hit?.dataset.slotId || null

    if (!insideView && !slotId) {
      clampScroll(
        viewport,
        (localX / mapRect.width) * v.sw - v.cw / 2,
        (localY / mapRect.height) * v.sh - v.ch / 2,
      )
    }

    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      startSl: viewport.scrollLeft,
      startSt: viewport.scrollTop,
      mapW: mapRect.width,
      mapH: mapRect.height,
      moved: false,
      slotId,
    }
  }

  function onPointerMove(e: ReactPointerEvent<HTMLDivElement>) {
    const drag = dragRef.current
    const viewport = findViewport(rootRef.current)
    if (!drag || !viewport) return
    const dx = e.clientX - drag.startX
    const dy = e.clientY - drag.startY
    if (!drag.moved && Math.abs(dx) < 3 && Math.abs(dy) < 3) return
    drag.moved = true
    clampScroll(
      viewport,
      drag.startSl + (dx / drag.mapW) * viewport.scrollWidth,
      drag.startSt + (dy / drag.mapH) * viewport.scrollHeight,
    )
  }

  function onPointerUp(e: ReactPointerEvent<HTMLDivElement>) {
    const drag = dragRef.current
    dragRef.current = null
    try {
      mapRef.current?.releasePointerCapture(e.pointerId)
    } catch {
      /* ignore */
    }
    if (!drag || drag.moved) return
    if (drag.slotId) onNavigateSlot(drag.slotId)
  }

  const box = sizeFor(view.sw, view.sh)
  const viewLeft = (view.sl / view.sw) * 100
  const viewTop = (view.st / view.sh) * 100
  const viewW = Math.min(100, (view.cw / view.sw) * 100)
  const viewH = Math.min(100, (view.ch / view.sh) * 100)
  const colW = weights?.cols ?? [1, ...classes.map(() => 1)]
  const rowH = weights?.rows ?? [1, ...rows.map((r) => (r.kind === 'day' ? 0.45 : 1))]
  const bodyRows = rowH.slice(1)

  if (!open) {
    return (
      <aside ref={rootRef} className="schedule-minimap is-collapsed">
        <button
          type="button"
          className="schedule-minimap-fab"
          title="Показать миникарту"
          aria-label="Показать миникарту"
          onClick={toggle}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <i className="bi bi-map" aria-hidden />
        </button>
      </aside>
    )
  }

  return (
    <aside
      ref={rootRef}
      className="schedule-minimap"
      style={{ width: box.w, height: box.h }}
      aria-label="Миникарта расписания"
    >
      <button
        type="button"
        className="schedule-minimap-hide"
        title="Скрыть миникарту"
        aria-label="Скрыть миникарту"
        onClick={toggle}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <i className="bi bi-chevron-down" aria-hidden />
      </button>
      <div
        ref={mapRef}
        className="schedule-minimap-map"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onWheel={onWheel}
      >
        <div className="schedule-minimap-row is-head" style={{ flexGrow: rowH[0] ?? 1 }}>
          {colW.map((w, i) => (
            <div
              key={i === 0 ? 'index' : classes[i - 1]?.id ?? i}
              className={i === 0 ? 'schedule-minimap-index' : 'schedule-minimap-colhead'}
              style={{ flexGrow: w }}
              title={i === 0 ? undefined : classes[i - 1]?.name}
            />
          ))}
        </div>
        {rows.map((row, idx) => {
          const grow = bodyRows[idx] ?? (row.kind === 'day' ? 0.45 : 1)
          if (row.kind === 'day') {
            return (
              <div
                key={`d-${row.day}`}
                className="schedule-minimap-row is-day"
                style={{ flexGrow: grow }}
                title={dayNames[row.day - 1]}
              />
            )
          }
          const lesson = row.kind === 'class_hour' ? 0 : row.lesson
          return (
            <div
              key={`r-${idx}`}
              className={`schedule-minimap-row${row.kind === 'class_hour' ? ' is-class-hour' : ''}`}
              style={{ flexGrow: grow }}
            >
              <div className="schedule-minimap-index" style={{ flexGrow: colW[0] ?? 1 }} />
              {classes.map((c, ci) => {
                const key = `${c.id}:${row.day}:${lesson}`
                const cells = cellsBySlot.get(key) ?? []
                const slotId = slotAnchor(c.id, row.day, lesson)
                return (
                  <div
                    key={c.id}
                    className="schedule-minimap-cell"
                    data-slot-id={slotId}
                    style={{ flexGrow: colW[ci + 1] ?? 1 }}
                    title={
                      cells.length
                        ? cells.map(lessonTitle).join('\n')
                        : `${c.name} · ${dayNames[row.day - 1]} · ${
                            row.kind === 'class_hour' ? 'классный час' : `урок ${lesson}`
                          }`
                    }
                  >
                    {cells.map((cell) => (
                      <span
                        key={cell.id}
                        className="schedule-minimap-lesson"
                        data-teacher-key={teacherHoverKey(cell) || undefined}
                        data-slot-id={slotId}
                        style={{ ['--lesson-color' as string]: cell.subject_color }}
                      />
                    ))}
                  </div>
                )
              })}
            </div>
          )
        })}
        <div
          className="schedule-minimap-view"
          style={{
            left: `${viewLeft}%`,
            top: `${viewTop}%`,
            width: `${viewW}%`,
            height: `${viewH}%`,
          }}
        />
      </div>
    </aside>
  )
}
