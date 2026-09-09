import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { memo, useCallback, useEffect, useMemo, useRef, useState, type DragEvent as ReactDragEvent, type PointerEvent as ReactPointerEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { OverlayScrollArea } from '../components/OverlayScrollArea'
import { ModalPortal } from '../components/ModalPortal'
import { ScheduleMinimap } from '../components/ScheduleMinimap'
import { TeacherDayGrid } from '../components/TeacherDayGrid'
import {
  ClassRemainingTip,
  type ClassRemaining,
  type ClassRemainingSubject,
} from '../components/ClassRemainingTip'
import { TeacherRemainingTip } from '../components/TeacherRemainingTip'
import { extractApiError } from '../api/client'
import {
  clearSchedule,
  createScheduleCell,
  deleteScheduleCell,
  explainSlot,
  fetchAssignmentsForClass,
  fetchGrid,
  fetchTeacherDay,
  swapScheduleClassrooms,
  updateScheduleCell,
  type ClassroomChoice,
  type GridData,
  type ScheduleCell as CellOut,
  type TeacherRemaining,
} from '../api/schedule'
import type { SchoolLevel } from '../domain/schoolLevel'
import { assignmentCanJoinSlot, slotAcceptsAnotherLesson } from '../domain/scheduleRules'
import { occupantsAtSlot, roomAllows, roomFreeAtSlot } from '../domain/classroomRules'
import { useScheduleExpand } from '../layouts/ScheduleLayout'

type SlotKey = { class_id: number; day: number; lesson: number; class_name: string }
type ScheduleDensity = 'compact' | 'comfortable'
type GridRow =
  | { kind: 'day'; day: number }
  | { kind: 'class_hour'; day: number }
  | { kind: 'lesson'; day: number; lesson: number }

const SHOW_OCCUPIED_VALUE = '__show_occupied__'
const SWAP_VALUE_PREFIX = 'swap:'
const EMPTY_CELLS: CellOut[] = []

const DENSITY_KEY = 'schedule:density'

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

function loadDensity(): ScheduleDensity {
  try {
    return localStorage.getItem(DENSITY_KEY) === 'comfortable' ? 'comfortable' : 'compact'
  } catch {
    return 'compact'
  }
}

function saveDensity(next: ScheduleDensity) {
  try {
    localStorage.setItem(DENSITY_KEY, next)
  } catch {
    /* ignore */
  }
}

function shortTeacherName(full: string | null | undefined): string {
  const name = (full ?? '').trim()
  if (!name) return '?'
  const parts = name.split(/\s+/).filter(Boolean)
  if (parts.length === 1) return parts[0]
  const initials = parts
    .slice(1)
    .map((p) => {
      const ch = [...p][0]
      return ch ? `${ch.toUpperCase()}.` : ''
    })
    .join('')
  return initials ? `${parts[0]} ${initials}` : parts[0]
}

/** Room number only — strip trailing « (Название)» from Classroom.display_name. */
function classroomNumberLabel(name: string | null | undefined): string {
  const raw = (name ?? '').trim()
  if (!raw) return ''
  const m = raw.match(/^(.+?)\s*\([^)]*\)\s*$/)
  return (m ? m[1] : raw).trim()
}

function lessonCardTitle(cell: CellOut): string {
  const bits = [cell.subject_name]
  if (cell.group_number != null) bits.push(`гр.${cell.group_number}`)
  if (cell.teacher_name) bits.push(cell.teacher_name)
  const room = classroomNumberLabel(cell.classroom_name)
  if (room) bits.push(`каб. ${room}`)
  return bits.join(' · ')
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
      const root = `.schedule-grid-card[data-hover-teacher="${a}"]`
      const match = `.lesson-card[data-teacher-key="${a}"]`
      const mini = `.schedule-minimap-lesson[data-teacher-key="${a}"]`
      const slotIdx = `tr[data-teachers~="${a}"] > .schedule-slot-index`
      return `${root} ${match}{background:color-mix(in srgb, var(--kivi-primary) 22%, var(--kivi-surface))!important;box-shadow:inset 0 0 0 3px var(--kivi-primary);opacity:1;position:relative;z-index:2}
${root} ${match} .teacher-name{color:var(--kivi-primary-deep);font-weight:700}
html[data-theme='dark'] ${root} ${match} .teacher-name{color:var(--kivi-primary)}
${root} ${mini}{opacity:1;filter:none;box-shadow:0 0 0 1px var(--kivi-primary),0 0 6px color-mix(in srgb, var(--kivi-primary) 65%, transparent);transform:scale(1.25);z-index:2;position:relative}
${root} ${slotIdx}{background:color-mix(in srgb, var(--kivi-primary) 22%, var(--kivi-surface))!important;box-shadow:inset 0 0 0 2px var(--kivi-primary),1px 0 0 var(--kivi-line);z-index:3}
${root} ${slotIdx} .schedule-slot-num,${root} ${slotIdx} .schedule-bell{color:var(--kivi-primary-deep);font-weight:700}
html[data-theme='dark'] ${root} ${slotIdx} .schedule-slot-num,html[data-theme='dark'] ${root} ${slotIdx} .schedule-bell{color:var(--kivi-primary)}`
    })
    .join('\n')
}

function teacherKeysForRow(
  classes: { id: number }[],
  day: number,
  lesson: number,
  cellsBySlot: Map<string, CellOut[]>,
): string {
  const keys = new Set<string>()
  for (const c of classes) {
    const cells = cellsBySlot.get(`${c.id}:${day}:${lesson}`)
    if (!cells) continue
    for (const cell of cells) {
      const key = teacherHoverKey(cell)
      if (key) keys.add(key)
    }
  }
  return [...keys].join(' ')
}

function applyTeacherHover(
  root: HTMLElement | null,
  key: string | null,
  slotId: string | null = null,
) {
  if (!root) return
  const nextKey = key || null
  const nextSlot = nextKey && slotId ? slotId : null
  const prevKey = root.getAttribute('data-hover-teacher')
  const prevSlot = root.getAttribute('data-hover-slot')
  if ((nextKey ?? '') === (prevKey ?? '') && (nextSlot ?? '') === (prevSlot ?? '')) return
  if (nextKey) root.setAttribute('data-hover-teacher', nextKey)
  else root.removeAttribute('data-hover-teacher')
  if (nextSlot) root.setAttribute('data-hover-slot', nextSlot)
  else root.removeAttribute('data-hover-slot')
  root.classList.toggle('is-teacher-hover', Boolean(nextKey))
}

function applyClassHover(root: HTMLElement | null, classId: string | null) {
  if (!root) return
  const next = classId || null
  const prev = root.getAttribute('data-hover-class')
  if ((next ?? '') === (prev ?? '')) return
  root.querySelector('th.is-class-hover-target')?.classList.remove('is-class-hover-target')
  if (next) {
    root.setAttribute('data-hover-class', next)
    root
      .querySelector(`th[data-class-id="${typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(next) : next}"]`)
      ?.classList.add('is-class-hover-target')
  } else {
    root.removeAttribute('data-hover-class')
  }
  root.classList.toggle('is-class-hover', Boolean(next))
}

function hoverTeacherFromEvent(target: EventTarget | null) {
  if (!(target instanceof Element)) return null
  const el = target.closest('[data-teacher-key]') as HTMLElement | null
  return el?.dataset.teacherKey || null
}

function hoverClassFromEvent(target: EventTarget | null) {
  if (!(target instanceof Element)) return null
  const el = target.closest('th[data-class-id]') as HTMLElement | null
  return el?.dataset.classId || null
}

function hoverSlotFromEvent(target: EventTarget | null) {
  if (!(target instanceof Element)) return null
  const slotted = target.closest('[data-slot-id]') as HTMLElement | null
  if (slotted?.dataset.slotId) return slotted.dataset.slotId
  const td = target.closest('td[id^="slot-"]') as HTMLElement | null
  return td?.id && td.id.startsWith('slot-') ? td.id : null
}

function applyGridHover(root: HTMLElement | null, target: EventTarget | null) {
  if (!root) return
  const classId = hoverClassFromEvent(target)
  if (classId) {
    applyTeacherHover(root, null)
    applyClassHover(root, classId)
    return
  }
  applyClassHover(root, null)
  applyTeacherHover(root, hoverTeacherFromEvent(target), hoverSlotFromEvent(target))
}

function buildClassRemainingById(
  classes: { id: number; name: string }[],
  teacherRemaining: TeacherRemaining[] | undefined,
): Map<number, ClassRemaining> {
  const m = new Map<number, ClassRemaining>()
  for (const c of classes) {
    m.set(c.id, {
      class_id: c.id,
      class_name: c.name,
      remaining_hours: 0,
      subjects: [],
    })
  }
  for (const teacher of teacherRemaining ?? []) {
    for (const row of teacher.classes) {
      let bucket = m.get(row.class_id)
      if (!bucket) {
        bucket = {
          class_id: row.class_id,
          class_name: row.class_name,
          remaining_hours: 0,
          subjects: [],
        }
        m.set(row.class_id, bucket)
      }
      bucket.remaining_hours += row.remaining_hours
      for (const subject of row.subjects) {
        const entry: ClassRemainingSubject = {
          ...subject,
          teacher_name: teacher.teacher_name,
        }
        bucket.subjects.push(entry)
      }
    }
  }
  for (const bucket of m.values()) {
    bucket.subjects.sort((a, b) =>
      a.subject_name.localeCompare(b.subject_name, 'ru') ||
      (a.group_number ?? 0) - (b.group_number ?? 0) ||
      a.teacher_name.localeCompare(b.teacher_name, 'ru'),
    )
  }
  return m
}

function gridQueryKey(level: SchoolLevel, shiftId: number | null) {
  return ['schedule', 'grid', level, shiftId] as const
}

function upsertCell(cells: CellOut[], cell: CellOut) {
  const i = cells.findIndex((c) => c.id === cell.id)
  if (i === -1) return [...cells, cell]
  if (cells[i] === cell) return cells
  const next = cells.slice()
  next[i] = cell
  return next
}

function removeCellById(cells: CellOut[], cellId: number) {
  return cells.some((c) => c.id === cellId) ? cells.filter((c) => c.id !== cellId) : cells
}

function patchRemainingSubjects(
  subjects: TeacherRemaining['classes'][number]['subjects'],
  cell: CellOut,
  delta: number,
) {
  const idx = subjects.findIndex(
    (s) => s.subject_name === cell.subject_name && s.group_number === cell.group_number,
  )
  if (idx === -1) {
    if (delta <= 0) return subjects
    return [
      ...subjects,
      {
        subject_name: cell.subject_name,
        remaining_hours: delta,
        group_number: cell.group_number,
      },
    ]
  }
  const hours = subjects[idx].remaining_hours + delta
  if (hours <= 0) return subjects.filter((_, i) => i !== idx)
  const next = subjects.slice()
  next[idx] = { ...subjects[idx], remaining_hours: hours }
  return next
}

function patchTeacherRemaining(
  rows: TeacherRemaining[] | undefined,
  cell: CellOut,
  delta: number,
  className: string,
): TeacherRemaining[] | undefined {
  if (!rows || cell.teacher_id == null || delta === 0) return rows
  let found = false
  const next = rows.map((row) => {
    if (row.teacher_id !== cell.teacher_id) return row
    found = true
    const remaining_hours = Math.max(0, row.remaining_hours + delta)
    const classIdx = row.classes.findIndex((c) => c.class_id === cell.class_id)
    let classes = row.classes
    if (classIdx === -1) {
      if (delta > 0) {
        classes = [
          ...row.classes,
          {
            class_id: cell.class_id,
            class_name: className,
            remaining_hours: delta,
            subjects: patchRemainingSubjects([], cell, delta),
          },
        ]
      }
    } else {
      const cur = row.classes[classIdx]
      const classHours = cur.remaining_hours + delta
      if (classHours <= 0) {
        classes = row.classes.filter((_, i) => i !== classIdx)
      } else {
        classes = row.classes.slice()
        classes[classIdx] = {
          ...cur,
          remaining_hours: classHours,
          subjects: patchRemainingSubjects(cur.subjects, cell, delta),
        }
      }
    }
    return { ...row, remaining_hours, classes }
  })
  if (found) return next
  if (delta <= 0) return rows
  return [
    ...rows,
    {
      teacher_id: cell.teacher_id,
      teacher_name: cell.teacher_name ?? '',
      remaining_hours: Math.max(0, delta),
      classes: [
        {
          class_id: cell.class_id,
          class_name: className,
          remaining_hours: delta,
          subjects: patchRemainingSubjects([], cell, delta),
        },
      ],
    },
  ]
}

function cellsVisualEq(a: CellOut[], b: CellOut[]) {
  if (a === b) return true
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    const x = a[i]
    const y = b[i]
    if (x === y) continue
    if (
      x.id !== y.id ||
      x.subject_name !== y.subject_name ||
      x.subject_color !== y.subject_color ||
      x.teacher_id !== y.teacher_id ||
      x.teacher_name !== y.teacher_name ||
      x.classroom_name !== y.classroom_name ||
      x.group_number !== y.group_number
    ) {
      return false
    }
  }
  return true
}

type SlotCellProps = {
  classId: number
  className: string
  day: number
  lesson: number
  cells: CellOut[]
  density: ScheduleDensity
  locked: boolean
  draggedCellId: { current: number | null }
  onOpenAdd: (classId: number, className: string, day: number, lesson: number) => void
  onOpenEdit: (cell: CellOut) => void
  onOpenWhy: (cell: CellOut) => void
  onDelete: (cell: CellOut) => void
  onDrop: (
    e: ReactDragEvent,
    target: { class_id: number; day: number; lesson: number },
  ) => void
}

const ScheduleSlotCell = memo(function ScheduleSlotCell(props: SlotCellProps) {
  const {
    classId,
    className,
    day,
    lesson,
    cells,
    density,
    locked,
    draggedCellId,
    onOpenAdd,
    onOpenEdit,
    onOpenWhy,
    onDelete,
    onDrop,
  } = props
  const canAdd = !locked && slotAcceptsAnotherLesson(cells)
  return (
    <td
      id={slotAnchor(classId, day, lesson)}
      className={`schedule-slot-cell align-top${locked ? ' is-locked' : ''}`}
      style={{ cursor: canAdd ? 'pointer' : 'default' }}
      title={locked && cells.length === 0 ? 'Классный час — урок поставить нельзя' : undefined}
      onDragOver={(e) => {
        if (locked) return
        e.preventDefault()
      }}
      onDrop={(e) => {
        if (locked) {
          e.preventDefault()
          return
        }
        onDrop(e, { class_id: classId, day, lesson })
      }}
      onClick={(e) => {
        if (locked) return
        if ((e.target as HTMLElement).closest('button, .lesson-card')) return
        if (!canAdd) return
        onOpenAdd(classId, className, day, lesson)
      }}
    >
      {cells.length === 0 ? (
        <div className={`schedule-slot-empty${locked ? ' is-locked' : ''}`} aria-hidden>
          {locked ? '' : '+'}
        </div>
      ) : (
        <>
          {cells.map((cell, i) => {
            const room = classroomNumberLabel(cell.classroom_name)
            return (
            <div
              key={cell.id}
              draggable
              data-teacher-key={teacherHoverKey(cell) || undefined}
              data-slot-id={slotAnchor(classId, day, lesson)}
              title={`${lessonCardTitle(cell)} · нажмите, чтобы сменить кабинет`}
              onDragStart={(e) => {
                applyTeacherHover(e.currentTarget.closest('.schedule-grid-card'), null)
                draggedCellId.current = cell.id
                e.dataTransfer.setData('text/cell-id', String(cell.id))
                e.dataTransfer.effectAllowed = 'move'
              }}
              className="lesson-card position-relative"
              style={{
                ['--lesson-color' as string]: cell.subject_color,
              }}
              onClick={(ev) => {
                ev.stopPropagation()
                if (draggedCellId.current === cell.id) {
                  draggedCellId.current = null
                  return
                }
                onOpenEdit(cell)
              }}
            >
              {i > 0 && density === 'comfortable' && <hr className="my-1" />}
              <div className="lesson-subject">
                {cell.subject_name}
                {cell.group_number != null && (
                  <span className="badge schedule-group-badge">гр.{cell.group_number}</span>
                )}
              </div>
              <div className="lesson-card-meta">
                <span className="teacher-name">
                  {density === 'compact'
                    ? shortTeacherName(cell.teacher_name)
                    : (cell.teacher_name ?? '?')}
                </span>
                {room ? (
                  <>
                    <span className="lesson-meta-sep" aria-hidden>
                      ·
                    </span>
                    <span className="lesson-room">
                      {density === 'compact' ? room : `каб. ${room}`}
                    </span>
                  </>
                ) : null}
              </div>
              <div className="lesson-card-actions">
                <button
                  type="button"
                  className="lesson-card-action"
                  title="Почему этот слот"
                  onPointerDown={suppressCardDrag}
                  onClick={(ev) => {
                    ev.stopPropagation()
                    onOpenWhy(cell)
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
                    onDelete(cell)
                  }}
                >
                  ×
                </button>
              </div>
            </div>
            )
          })}
          {canAdd && (
            <button
              type="button"
              className="slot-add-subgroup"
              title="Добавить вторую подгруппу"
              onClick={(ev) => {
                ev.stopPropagation()
                onOpenAdd(classId, className, day, lesson)
              }}
            >
              +
            </button>
          )}
        </>
      )}
    </td>
  )
}, (prev, next) => (
  prev.classId === next.classId &&
  prev.className === next.className &&
  prev.day === next.day &&
  prev.lesson === next.lesson &&
  prev.density === next.density &&
  prev.locked === next.locked &&
  prev.onOpenAdd === next.onOpenAdd &&
  prev.onOpenEdit === next.onOpenEdit &&
  prev.onOpenWhy === next.onOpenWhy &&
  prev.onDelete === next.onDelete &&
  prev.onDrop === next.onDrop &&
  cellsVisualEq(prev.cells, next.cells)
))

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

function gridViewport(): HTMLElement | null {
  return document.querySelector('.schedule-grid-card .overlay-scroll-viewport')
}

function restorePixels(top: number, left: number) {
  const viewport = gridViewport()
  if (!viewport || !viewportReady(viewport)) return false
  viewport.scrollTo({ top, left })
  if ((top > 8 && viewport.scrollTop < 8) || (left > 8 && viewport.scrollLeft < 8)) {
    return false
  }
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
      : storedTab?.shift_id ?? null
  const [toast, setToast] = useState<{ kind: 'success' | 'danger'; text: string } | null>(null)
  const [density, setDensity] = useState<ScheduleDensity>(loadDensity)
  const { expanded, setExpanded } = useScheduleExpand()
  const [slot, setSlot] = useState<SlotKey | null>(null)
  const [editCell, setEditCell] = useState<CellOut | null>(null)
  const [whyCell, setWhyCell] = useState<CellOut | null>(null)
  const draggedCellId = useRef<number | null>(null)
  const hashTimer = useRef<number>(0)
  const restoreDone = useRef(false)
  const syncAllowed = useRef(false)
  const pendingAnchor = useRef(bootAnchor)

  useEffect(() => {
    saveDensity(density)
  }, [density])

  function finishRestore() {
    restoreDone.current = true
    syncAllowed.current = true
  }

  function tryRestoreAnchor() {
    if (restoreDone.current) return true
    const saved = loadSavedView(level, shiftId)
    const liveHash = window.location.hash.replace(/^#/, '')
    const hash = liveHash || saved?.hash || pendingAnchor.current || ''
    const viewport = gridViewport()
    if (viewport && (viewport.scrollTop > 8 || viewport.scrollLeft > 8)) {
      finishRestore()
      return true
    }
    if (saved && (saved.top > 0 || saved.left > 0)) {
      if (restorePixels(saved.top, saved.left)) {
        if (saved.hash) replaceHash(saved.hash)
        finishRestore()
        return true
      }
      return false
    }
    if (hash.startsWith('slot-')) {
      if (scrollScheduleAnchor(hash, 'nearest')) {
        replaceHash(hash)
        finishRestore()
        return true
      }
      return false
    }
    if (hash.startsWith('day-') || hash.startsWith('class-')) {
      if (scrollScheduleAnchor(hash, 'start')) {
        replaceHash(hash)
        finishRestore()
        return true
      }
      return false
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
      const viewport = gridViewport()
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
    const viewport = gridViewport()
    if (!viewport) return
    const liveHash = window.location.hash.replace(/^#/, '')
    const days = viewport.querySelectorAll<HTMLElement>('[id^="day-"]')
    if (!days.length) return
    const sticky = viewport.querySelector('thead') as HTMLElement | null
    const viewTop =
      viewport.getBoundingClientRect().top + (sticky?.getBoundingClientRect().height ?? 0) + 8
    let current = days[0].id
    days.forEach((el) => {
      if (el.getBoundingClientRect().top <= viewTop) current = el.id
    })
    const hash = liveHash.startsWith('slot-') ? liveHash : current
    saveSavedView(level, shiftId, {
      hash,
      top: viewport.scrollTop,
      left: viewport.scrollLeft,
    })
    window.clearTimeout(hashTimer.current)
    hashTimer.current = window.setTimeout(() => {
      if (window.location.hash !== `#${hash}`) replaceHash(hash)
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

  const teacherHoverKeySig = useMemo(
    () =>
      [...new Set((gridQ.data?.cells ?? []).map(teacherHoverKey).filter(Boolean))]
        .sort()
        .join('\n'),
    [gridQ.data?.cells],
  )
  const teacherHoverCss = useMemo(
    () => (teacherHoverKeySig ? buildTeacherHoverCss(teacherHoverKeySig.split('\n')) : ''),
    [teacherHoverKeySig],
  )

  const remainingByKey = useMemo(() => {
    const m = new Map<string, TeacherRemaining>()
    for (const row of gridQ.data?.teacher_remaining ?? []) {
      const key = teacherHoverKey(row)
      if (key) m.set(key, row)
    }
    return m
  }, [gridQ.data?.teacher_remaining])

  const remainingByClassId = useMemo(
    () => buildClassRemainingById(gridQ.data?.classes ?? [], gridQ.data?.teacher_remaining),
    [gridQ.data?.classes, gridQ.data?.teacher_remaining],
  )

  const occupiedForModal = useMemo(() => {
    if (!slot || !gridQ.data) return [] as CellOut[]
    return gridQ.data.cells.filter(
      (c) =>
        c.class_id === slot.class_id &&
        c.day_of_week === slot.day &&
        c.lesson_number === slot.lesson,
    )
  }, [slot, gridQ.data])

  const classNameById = useMemo(() => {
    const m: Record<number, string> = {}
    for (const c of gridQ.data?.classes ?? []) m[c.id] = c.name
    return m
  }, [gridQ.data?.classes])

  function patchGrid(updater: (grid: GridData) => GridData) {
    qc.setQueryData<GridData>(gridQueryKey(level, shiftId), (old) => (old ? updater(old) : old))
  }

  function afterCellWrite() {
    void qc.invalidateQueries({ queryKey: ['schedule', 'assignments-for-class'] })
    void qc.invalidateQueries({ queryKey: ['schedule', 'teacher-day'] })
  }

  const addM = useMutation({
    mutationFn: async (p: {
      class_id: number
      day_of_week: number
      lesson_number: number
      assignment_id: number
      classroom_id: number | null
    }) => createScheduleCell(p),
    onSuccess: (cell, p) => {
      setSlot(null)
      setToast({ kind: 'success', text: 'Урок добавлен' })
      replaceHash(slotAnchor(p.class_id, p.day_of_week, p.lesson_number))
      patchGrid((grid) => ({
        ...grid,
        cells: upsertCell(grid.cells, cell),
        teacher_remaining: patchTeacherRemaining(
          grid.teacher_remaining,
          cell,
          -1,
          grid.classes.find((c) => c.id === cell.class_id)?.name ?? '',
        ),
      }))
      afterCellWrite()
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
    onSuccess: (cell, p) => {
      setToast({ kind: 'success', text: 'Урок перемещён' })
      replaceHash(slotAnchor(p.class_id, p.day_of_week, p.lesson_number))
      patchGrid((grid) => ({ ...grid, cells: upsertCell(grid.cells, cell) }))
      afterCellWrite()
      stayAt(p.class_id, p.day_of_week, p.lesson_number)
    },
    onError: (e) => setToast({ kind: 'danger', text: extractApiError(e) }),
  })

  const delM = useMutation({
    mutationFn: (p: { cell_id: number; class_id: number; day: number; lesson: number }) =>
      deleteScheduleCell(p.cell_id),
    onSuccess: (_ok, p) => {
      setToast({ kind: 'success', text: 'Урок удалён' })
      replaceHash(slotAnchor(p.class_id, p.day, p.lesson))
      patchGrid((grid) => {
        const removed = grid.cells.find((c) => c.id === p.cell_id)
        const cells = removeCellById(grid.cells, p.cell_id)
        if (!removed) return { ...grid, cells }
        return {
          ...grid,
          cells,
          teacher_remaining: patchTeacherRemaining(
            grid.teacher_remaining,
            removed,
            1,
            grid.classes.find((c) => c.id === removed.class_id)?.name ?? '',
          ),
        }
      })
      afterCellWrite()
      stayAt(p.class_id, p.day, p.lesson)
    },
    onError: (e) => setToast({ kind: 'danger', text: extractApiError(e) }),
  })

  const clearDayM = useMutation({
    mutationFn: (p: { day: number; shiftId: number | null; classIds: number[] }) =>
      clearSchedule({
        school_level: level,
        days_of_week: [p.day],
        class_ids: p.classIds,
        ...(p.shiftId != null ? { shift_id: p.shiftId } : {}),
      }),
    onSuccess: async (res, p) => {
      const name = gridQ.data?.day_names[p.day - 1] ?? ''
      const shiftName = gridQ.data?.current_shift?.name
      setToast({
        kind: 'success',
        text: name
          ? shiftName
            ? `Удалено уроков ${shiftName} за ${name.toLowerCase()}: ${res.count}`
            : `Удалено уроков за ${name.toLowerCase()}: ${res.count}`
          : `Удалено уроков: ${res.count}`,
      })
      await qc.invalidateQueries({ queryKey: ['schedule', 'grid'] })
    },
    onError: (e) => setToast({ kind: 'danger', text: extractApiError(e) }),
  })

  const changeRoomM = useMutation({
    mutationFn: async (p: {
      cell: CellOut
      classroom_id: number | null
    }) =>
      updateScheduleCell(p.cell.id, {
        day_of_week: p.cell.day_of_week,
        lesson_number: p.cell.lesson_number,
        class_id: p.cell.class_id,
        classroom_id: p.classroom_id,
        set_classroom: true,
      }),
    onSuccess: (cell, p) => {
      setEditCell(null)
      setToast({ kind: 'success', text: 'Кабинет изменён' })
      replaceHash(slotAnchor(p.cell.class_id, p.cell.day_of_week, p.cell.lesson_number))
      patchGrid((grid) => ({ ...grid, cells: upsertCell(grid.cells, cell) }))
      afterCellWrite()
      stayAt(p.cell.class_id, p.cell.day_of_week, p.cell.lesson_number)
    },
  })

  const swapRoomM = useMutation({
    mutationFn: async (p: { cell: CellOut; other: CellOut }) =>
      swapScheduleClassrooms(p.cell.id, p.other.id),
    onSuccess: (res, p) => {
      setEditCell(null)
      setToast({ kind: 'success', text: 'Учителя поменялись кабинетами' })
      replaceHash(slotAnchor(p.cell.class_id, p.cell.day_of_week, p.cell.lesson_number))
      patchGrid((grid) => {
        let cells = upsertCell(grid.cells, res.cell)
        cells = upsertCell(cells, res.other)
        return { ...grid, cells }
      })
      afterCellWrite()
      stayAt(p.cell.class_id, p.cell.day_of_week, p.cell.lesson_number)
    },
  })

  const openAdd = useCallback(
    (classId: number, className: string, day: number, lesson: number) => {
      if (lesson === 0) return
      setSlot({ class_id: classId, day, lesson, class_name: className })
    },
    [setSlot],
  )
  const openEdit = useCallback((cell: CellOut) => setEditCell(cell), [setEditCell])
  const openWhy = useCallback((cell: CellOut) => setWhyCell(cell), [setWhyCell])
  const deleteCell = useCallback((cell: CellOut) => {
    if (!confirm('Удалить урок?')) return
    delM.mutate({
      cell_id: cell.id,
      class_id: cell.class_id,
      day: cell.day_of_week,
      lesson: cell.lesson_number,
    })
  }, [delM.mutate])
  const onDropSlot = useCallback(
    (e: ReactDragEvent, target: { class_id: number; day: number; lesson: number }) => {
      e.preventDefault()
      if (target.lesson === 0) return
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
    },
    [moveM.mutate],
  )
  const navigateMinimapSlot = useCallback((id: string) => {
    scrollScheduleAnchor(id, 'nearest')
  }, [])

  const cellsBySlot = useMemo(() => {
    const m = new Map<string, CellOut[]>()
    for (const c of gridQ.data?.cells ?? []) {
      const key = `${c.class_id}:${c.day_of_week}:${c.lesson_number}`
      const arr = m.get(key)
      if (arr) arr.push(c)
      else m.set(key, [c])
    }
    return m
  }, [gridQ.data?.cells])

  const rows = useMemo(() => {
    const grid = gridQ.data
    const out: GridRow[] = []
    if (!grid) return out
    for (let day = 1; day <= grid.working_days; day++) {
      out.push({ kind: 'day', day })
      if (
        grid.current_shift &&
        grid.current_shift.class_hour_day === day &&
        grid.class_hour_time_label
      ) {
        out.push({ kind: 'class_hour', day })
      }
      for (const lesson of grid.lessons_range) {
        const classHourLessons = grid.current_shift?.class_hour_lessons_count
        const startLesson = grid.current_shift?.start_lesson ?? 1
        if (
          grid.current_shift?.class_hour_day === day &&
          classHourLessons != null &&
          classHourLessons > 0 &&
          lesson >= startLesson + classHourLessons
        ) {
          continue
        }
        out.push({ kind: 'lesson', day, lesson })
      }
    }
    return out
  }, [
    gridQ.data?.working_days,
    gridQ.data?.lessons_range,
    gridQ.data?.current_shift,
    gridQ.data?.class_hour_time_label,
  ])

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
  }, [gridQ.data?.classes, level, shiftId])

  if (gridQ.isPending && !gridQ.data) return <p>Загрузка…</p>
  if (gridQ.isError) return <p className="text-danger">{extractApiError(gridQ.error)}</p>

  const grid = gridQ.data!

  return (
    <div className={`schedule-grid-page is-${density}${expanded ? ' is-expanded' : ''}`}>
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

        <div className="schedule-grid-view-controls">
          <div className="schedule-density" role="group" aria-label="Плотность сетки">
            <button
              type="button"
              className={density === 'compact' ? 'is-active' : ''}
              aria-pressed={density === 'compact'}
              onClick={() => setDensity('compact')}
            >
              Плотно
            </button>
            <button
              type="button"
              className={density === 'comfortable' ? 'is-active' : ''}
              aria-pressed={density === 'comfortable'}
              onClick={() => setDensity('comfortable')}
            >
              Обычно
            </button>
          </div>
          {expanded && (
            <button
              type="button"
              className="btn btn-dark btn-sm schedule-expand-btn"
              title="Свернуть таблицу"
              aria-label="Свернуть таблицу"
              onClick={() => setExpanded(false)}
            >
              <i className="bi bi-arrows-angle-contract" />
              <span className="ms-1">Свернуть</span>
            </button>
          )}
        </div>
      </div>

      {grid.classes.length === 0 ? (
        <div className="card">
          <div className="card-body text-muted text-center py-5">
            Нет классов для отображения. Привяжите классы к смене.
          </div>
        </div>
      ) : (
        <div
          className="card schedule-grid-card"
          onMouseOver={(e) => {
            applyGridHover(e.currentTarget, e.target)
          }}
          onMouseOut={(e) => {
            const card = e.currentTarget
            const rel = e.relatedTarget
            if (rel instanceof Node && card.contains(rel)) {
              applyGridHover(card, rel)
              return
            }
            applyGridHover(card, null)
          }}
        >
          {teacherHoverCss ? <style>{teacherHoverCss}</style> : null}
          <TeacherRemainingTip remainingByKey={remainingByKey} />
          <ClassRemainingTip remainingByClassId={remainingByClassId} />
          <OverlayScrollArea
            key={`${level}-${shiftId ?? 'auto'}`}
            persistKey={`schedule-grid:${level}:${shiftId ?? 'auto'}`}
            onScroll={syncHashFromScroll}
            onViewportReady={() => {
              tryRestoreAnchor()
            }}
          >
            <table className={`table table-bordered mb-0 schedule-grid-table is-${density}`}>
              <thead className="table-light">
                <tr>
                  <th className="schedule-slot-index">Урок</th>
                  {grid.classes.map((c) => (
                    <th
                      key={c.id}
                      id={classAnchor(c.id)}
                      data-class-id={c.id}
                      className="text-center"
                    >
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
                          className="schedule-day-row"
                        >
                          <div className="schedule-day-row-inner">
                            <span>{grid.day_names[row.day - 1]}</span>
                            <button
                              type="button"
                              className="btn btn-outline-danger schedule-day-clear"
                              disabled={clearDayM.isPending}
                              title={
                                grid.current_shift
                                  ? `Удалить уроки ${grid.current_shift.name} в этот день`
                                  : `Удалить все уроки ${
                                      level === 'elementary' ? 'начальной' : 'основной'
                                    } школы в этот день`
                              }
                              onClick={(e) => {
                                e.stopPropagation()
                                const name = grid.day_names[row.day - 1]
                                const shift = grid.current_shift
                                const confirmText = shift
                                  ? `Удалить уроки смены «${shift.name}» в ${name.toLowerCase()}? Другие смены не изменятся.`
                                  : `Удалить все уроки ${
                                      level === 'elementary' ? 'начальной' : 'основной'
                                    } школы в ${name.toLowerCase()}?`
                                if (!confirm(confirmText)) {
                                  return
                                }
                                const classIds = grid.classes.map((c) => c.id)
                                if (classIds.length === 0) return
                                clearDayM.mutate({
                                  day: row.day,
                                  shiftId:
                                    grid.current_shift_id ??
                                    shiftId ??
                                    grid.shifts[0]?.id ??
                                    null,
                                  classIds,
                                })
                              }}
                            >
                              Очистить день
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  }
                  const lesson = row.kind === 'class_hour' ? 0 : row.lesson
                  const isClassHour = row.kind === 'class_hour'
                  const time = isClassHour
                    ? grid.class_hour_time_label
                    : grid.lesson_times_by_day[row.day]?.[lesson]
                  const rowTeachers = teacherKeysForRow(
                    grid.classes,
                    row.day,
                    lesson,
                    cellsBySlot,
                  )
                  return (
                    <tr
                      key={`r-${idx}`}
                      className={isClassHour ? 'is-class-hour' : undefined}
                      data-teachers={rowTeachers || undefined}
                    >
                      <td className="schedule-slot-index text-center align-middle">
                        <div
                          className="schedule-slot-num"
                          title={isClassHour ? 'Классный час' : undefined}
                        >
                          {isClassHour
                            ? density === 'compact'
                              ? 'Кл. час'
                              : 'Классный час'
                            : lesson}
                        </div>
                        {time ? <BellLabel time={time} /> : null}
                      </td>
                      {grid.classes.map((c) => (
                        <ScheduleSlotCell
                          key={c.id}
                          classId={c.id}
                          className={c.name}
                          day={row.day}
                          lesson={lesson}
                          cells={cellsBySlot.get(`${c.id}:${row.day}:${lesson}`) ?? EMPTY_CELLS}
                          density={density}
                          locked={isClassHour}
                          draggedCellId={draggedCellId}
                          onOpenAdd={openAdd}
                          onOpenEdit={openEdit}
                          onOpenWhy={openWhy}
                          onDelete={deleteCell}
                          onDrop={onDropSlot}
                        />
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </OverlayScrollArea>
          <ScheduleMinimap
            layoutKey={`${level}-${shiftId ?? 'auto'}`}
            classes={grid.classes}
            rows={rows}
            cellsBySlot={cellsBySlot}
            dayNames={grid.day_names}
            onNavigateSlot={navigateMinimapSlot}
          />
        </div>
      )}

      {slot && (
        <AddLessonModal
          slot={slot}
          occupied={occupiedForModal}
          cells={grid.cells}
          classSchoolLevel={level}
          classNameById={classNameById}
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

      {editCell && (
        <ChangeClassroomModal
          cell={editCell}
          cells={grid.cells}
          classSchoolLevel={level}
          classNameById={classNameById}
          dayNames={grid.day_names}
          error={
            changeRoomM.isError
              ? extractApiError(changeRoomM.error)
              : swapRoomM.isError
                ? extractApiError(swapRoomM.error)
                : null
          }
          onClose={() => {
            changeRoomM.reset()
            swapRoomM.reset()
            setEditCell(null)
          }}
          onChangeClassroom={(classroom_id) =>
            changeRoomM.mutate({ cell: editCell, classroom_id })
          }
          onSwap={(other) => swapRoomM.mutate({ cell: editCell, other })}
          submitting={changeRoomM.isPending || swapRoomM.isPending}
        />
      )}

      {whyCell && (
        <WhyCellModal cell={whyCell} onClose={() => setWhyCell(null)} />
      )}
    </div>
  )
}

function classroomAllows(
  room: ClassroomChoice,
  opts: {
    subject_id: number
    requires_fixed_classroom: boolean
    class_school_level: SchoolLevel
    is_subgroup: boolean
  },
) {
  return roomAllows(
    {
      id: room.id,
      subject_ids: room.subject_ids ?? [],
      is_exclusive: Boolean(room.is_exclusive),
      school_level: room.school_level ?? null,
      subgroup_only: Boolean(room.subgroup_only),
    },
    opts,
  )
}

function occupantLabel(cell: CellOut, classNameById: Record<number, string>): string {
  const cls = classNameById[cell.class_id] ?? `класс ${cell.class_id}`
  const teacher = cell.teacher_name ?? '?'
  return `${cls}, ${teacher}, ${cell.subject_name}`
}

function swapOptionValue(cellId: number) {
  return `${SWAP_VALUE_PREFIX}${cellId}`
}

function parseSwapOption(raw: string): number | null {
  if (!raw.startsWith(SWAP_VALUE_PREFIX)) return null
  const id = Number(raw.slice(SWAP_VALUE_PREFIX.length))
  return Number.isFinite(id) && id > 0 ? id : null
}

function swapConfirmText(
  cell: CellOut,
  other: CellOut,
  classNameById: Record<number, string>,
): string {
  const otherClass = classNameById[other.class_id] ?? `класс ${other.class_id}`
  const room = other.classroom_name ?? '?'
  const yours = cell.classroom_name
  const extra = yours
    ? `\nВаш кабинет ${yours} отойдёт ${otherClass}.`
    : `\nУрок ${otherClass} останется без кабинета.`
  return (
    `Кабинет ${room} занят: ${occupantLabel(other, classNameById)}.` +
    extra +
    '\n\nПоменять учителей местами?'
  )
}

type OccupiedRoomOption = {
  id: number
  display_name: string
  occupants: CellOut[]
  allowed: boolean
}

function occupiedRoomsFromCells(
  cells: CellOut[],
  slot: { day: number; lesson: number },
  excludeCellId?: number | null,
): OccupiedRoomOption[] {
  const byRoom = new Map<number, OccupiedRoomOption>()
  for (const cell of cells) {
    if (!cell.classroom_id) continue
    if (excludeCellId != null && cell.id === excludeCellId) continue
    if (cell.day_of_week !== slot.day || cell.lesson_number !== slot.lesson) continue
    const existing = byRoom.get(cell.classroom_id)
    if (existing) {
      existing.occupants.push(cell)
    } else {
      byRoom.set(cell.classroom_id, {
        id: cell.classroom_id,
        display_name: cell.classroom_name ?? String(cell.classroom_id),
        occupants: [cell],
        allowed: false,
      })
    }
  }
  return [...byRoom.values()]
}

function ClassroomPicker(props: {
  classroomId: number | ''
  selectedOccupantId?: number | null
  freeRooms: ClassroomChoice[]
  occupiedRooms: OccupiedRoomOption[]
  classNameById: Record<number, string>
  allowSelectOccupied: boolean
  onChangeFree: (id: number | '') => void
  onPickOccupied?: (occupant: CellOut) => void
}) {
  const {
    classroomId,
    selectedOccupantId,
    freeRooms,
    occupiedRooms,
    classNameById,
    allowSelectOccupied,
    onChangeFree,
    onPickOccupied,
  } = props
  const [showOccupied, setShowOccupied] = useState(Boolean(selectedOccupantId))
  const selectValue =
    selectedOccupantId != null
      ? swapOptionValue(selectedOccupantId)
      : classroomId === ''
        ? ''
        : String(classroomId)

  return (
    <>
    <select
      className="form-select"
      value={selectValue}
      onChange={(e) => {
        const raw = e.target.value
        if (raw === SHOW_OCCUPIED_VALUE) {
          setShowOccupied(true)
          return
        }
        if (raw.startsWith('occ-')) return
        const swapId = parseSwapOption(raw)
        if (swapId != null) {
          const occupant = occupiedRooms.flatMap((r) => r.occupants).find((c) => c.id === swapId)
          if (occupant && allowSelectOccupied) onPickOccupied?.(occupant)
          return
        }
        onChangeFree(raw === '' ? '' : Number(raw))
      }}
    >
      <option value="">Без кабинета</option>
      {freeRooms.map((c) => (
        <option key={c.id} value={c.id}>
          {c.display_name}
        </option>
      ))}
      {!showOccupied && occupiedRooms.length > 0 && (
        <option value={SHOW_OCCUPIED_VALUE}>Посмотреть занятые…</option>
      )}
      {showOccupied && occupiedRooms.length > 0 && (
        <optgroup label="Занятые">
          {occupiedRooms.flatMap((room) =>
            room.occupants.map((occ) => {
              const selectable = allowSelectOccupied && room.allowed
              return (
                <option
                  key={occ.id}
                  value={selectable ? swapOptionValue(occ.id) : `occ-${occ.id}`}
                  disabled={!selectable}
                >
                  {room.display_name} — {occupantLabel(occ, classNameById)}
                  {selectable ? '' : ' (занят)'}
                </option>
              )
            }),
          )}
        </optgroup>
      )}
    </select>
    {showOccupied && occupiedRooms.length > 0 && (
      <div className="form-text mt-2">
        {occupiedRooms.flatMap((room) =>
          room.occupants.map((occ) => (
            <div key={occ.id}>
              {room.display_name} — {occupantLabel(occ, classNameById)}
              {allowSelectOccupied && room.allowed ? (
                <>
                  {' '}
                  <button
                    type="button"
                    className="btn btn-link btn-sm p-0 align-baseline"
                    onClick={() => onPickOccupied?.(occ)}
                  >
                    поменять местами
                  </button>
                </>
              ) : null}
            </div>
          )),
        )}
      </div>
    )}
    </>
  )
}

function AddLessonModal(props: {
  slot: SlotKey
  occupied: CellOut[]
  cells: CellOut[]
  classSchoolLevel: SchoolLevel
  classNameById: Record<number, string>
  dayNames: string[]
  error: string | null
  onClose: () => void
  onSubmit: (assignment_id: number, classroom_id: number | null) => void
  submitting: boolean
}) {
  const { slot, occupied, cells, classSchoolLevel, classNameById, dayNames, error, onClose, onSubmit, submitting } = props
  const occupiedSubject =
    occupied.length > 0 && occupied.every((c) => c.subject_name === occupied[0].subject_name)
      ? occupied[0].subject_name
      : ''
  const [subjectName, setSubjectName] = useState<string>(occupiedSubject)
  const [assignmentId, setAssignmentId] = useState<number | ''>('')
  const [classroomId, setClassroomId] = useState<number | ''>('')

  const q = useQuery({
    queryKey: ['schedule', 'assignments-for-class', slot.class_id, slot.day, slot.lesson],
    queryFn: () => fetchAssignmentsForClass(slot.class_id, { day: slot.day, lesson: slot.lesson }),
  })

  const compatibleAssignments = useMemo(
    () => q.data?.assignments.filter((a) => assignmentCanJoinSlot(a, occupied)) ?? [],
    [q.data, occupied],
  )

  const subjects = useMemo(() => {
    const m = new Map<string, string>()
    for (const a of compatibleAssignments) {
      if (!m.has(a.subject_name)) m.set(a.subject_name, a.subject_color)
    }
    return [...m.entries()].map(([name, color]) => ({ name, color }))
  }, [compatibleAssignments])

  const filteredAssignments = useMemo(
    () => compatibleAssignments.filter((a) => a.subject_name === subjectName),
    [compatibleAssignments, subjectName],
  )

  const selectedAssignment = useMemo(
    () =>
      typeof assignmentId === 'number'
        ? filteredAssignments.find((a) => a.id === assignmentId) ?? null
        : null,
    [filteredAssignments, assignmentId],
  )

  const teacherId = selectedAssignment?.teacher_id ?? null
  const teacherDayQ = useQuery({
    queryKey: ['schedule', 'teacher-day', teacherId, slot.class_id, slot.day, slot.lesson],
    queryFn: () =>
      fetchTeacherDay({
        teacherId: teacherId as number,
        day: slot.day,
        classId: slot.class_id,
        lesson: slot.lesson,
      }),
    enabled: teacherId != null,
  })

  const allowedClassrooms = useMemo(() => {
    const rooms = q.data?.classrooms ?? []
    const free = rooms.filter((c) =>
      roomFreeAtSlot(c, cells, { day: slot.day, lesson: slot.lesson }),
    )
    if (!selectedAssignment) return free
    return free.filter((c) =>
      classroomAllows(c, {
        subject_id: selectedAssignment.subject_id,
        requires_fixed_classroom: Boolean(selectedAssignment.requires_fixed_classroom),
        class_school_level: classSchoolLevel,
        is_subgroup: selectedAssignment.group_number != null,
      }),
    )
  }, [q.data?.classrooms, selectedAssignment, classSchoolLevel, cells, slot.day, slot.lesson])

  const occupiedRooms = useMemo(
    () => occupiedRoomsFromCells(cells, { day: slot.day, lesson: slot.lesson }),
    [cells, slot.day, slot.lesson],
  )

  useEffect(() => {
    if (filteredAssignments.length === 1) {
      const only = filteredAssignments[0]
      setAssignmentId(only.id)
      if (only.preferred_classroom_id) {
        const room = (q.data?.classrooms ?? []).find((c) => c.id === only.preferred_classroom_id)
        if (room && roomFreeAtSlot(room, cells, { day: slot.day, lesson: slot.lesson })) {
          setClassroomId(only.preferred_classroom_id)
        }
      }
    } else {
      setAssignmentId('')
    }
  }, [filteredAssignments, q.data?.classrooms, cells, slot.day, slot.lesson])

  useEffect(() => {
    if (classroomId === '') return
    if (!allowedClassrooms.some((c) => c.id === classroomId)) {
      setClassroomId('')
    }
  }, [allowedClassrooms, classroomId])

  const slotLabel = slot.lesson === 0 ? 'классный час' : `урок ${slot.lesson}`
  const title = `${slot.class_name}, ${dayNames[slot.day - 1]}, ${slotLabel}`

  return (
    <ModalPortal>
    <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,.35)' }}>
      <div className="modal-dialog">
        <div className="modal-content">
          <div className="modal-header">
            <h5 className="modal-title">
              {occupied.length > 0 ? 'Добавить подгруппу' : 'Добавить урок'}
            </h5>
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
            {q.data && q.data.assignments.length > 0 && compatibleAssignments.length === 0 && (
              <div className="text-muted">
                В этой ячейке уже стоит подгруппа. Можно добавить только другую группу того же
                предмета — если у неё ещё есть нерасставленные часы.
              </div>
            )}
            {q.data && compatibleAssignments.length > 0 && (
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
                        const room = (q.data?.classrooms ?? []).find(
                          (c) => c.id === picked.preferred_classroom_id,
                        )
                        if (
                          room &&
                          roomFreeAtSlot(room, cells, { day: slot.day, lesson: slot.lesson })
                        ) {
                          setClassroomId(picked.preferred_classroom_id)
                        }
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
                {subjectName && assignmentId === '' && (
                  <div className="text-muted small mb-3">
                    Выберите учителя, чтобы увидеть его день в других сменах.
                  </div>
                )}
                {(teacherDayQ.isFetching || teacherDayQ.data || teacherDayQ.isError) && (
                  <div className="mb-3">
                    <TeacherDayGrid
                      data={teacherDayQ.data}
                      loading={teacherDayQ.isLoading}
                      error={
                        teacherDayQ.isError
                          ? extractApiError(teacherDayQ.error)
                          : null
                      }
                    />
                  </div>
                )}
                <div className="mb-3">
                  <label className="form-label fw-bold">Кабинет</label>
                  <ClassroomPicker
                    classroomId={classroomId}
                    freeRooms={allowedClassrooms}
                    occupiedRooms={occupiedRooms}
                    classNameById={classNameById}
                    allowSelectOccupied={false}
                    onChangeFree={setClassroomId}
                  />
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

function ChangeClassroomModal(props: {
  cell: CellOut
  cells: CellOut[]
  classSchoolLevel: SchoolLevel
  classNameById: Record<number, string>
  dayNames: string[]
  error: string | null
  onClose: () => void
  onChangeClassroom: (classroom_id: number | null) => void
  onSwap: (other: CellOut) => void
  submitting: boolean
}) {
  const {
    cell,
    cells,
    classSchoolLevel,
    classNameById,
    dayNames,
    error,
    onClose,
    onChangeClassroom,
    onSwap,
    submitting,
  } = props
  const [classroomId, setClassroomId] = useState<number | ''>(cell.classroom_id ?? '')
  const [swapWith, setSwapWith] = useState<CellOut | null>(null)

  const q = useQuery({
    queryKey: ['schedule', 'assignments-for-class', cell.class_id],
    queryFn: () => fetchAssignmentsForClass(cell.class_id),
  })

  const allowOpts = {
    subject_id: cell.subject_id,
    requires_fixed_classroom: Boolean(cell.requires_fixed_classroom),
    class_school_level: classSchoolLevel,
    is_subgroup: cell.group_number != null,
  }
  const slot = { day: cell.day_of_week, lesson: cell.lesson_number }

  const allowedRooms = useMemo(() => {
    const rooms = q.data?.classrooms ?? []
    return rooms.filter((c) => classroomAllows(c, allowOpts))
  }, [q.data?.classrooms, cell.subject_id, cell.requires_fixed_classroom, cell.group_number, classSchoolLevel])

  const freeRooms = useMemo(
    () => allowedRooms.filter((c) => roomFreeAtSlot(c, cells, slot, cell.id)),
    [allowedRooms, cells, cell.id, cell.day_of_week, cell.lesson_number],
  )

  const occupiedRooms = useMemo(() => {
    const byId = new Map<number, OccupiedRoomOption>()
    for (const room of occupiedRoomsFromCells(cells, slot, cell.id)) {
      byId.set(room.id, room)
    }
    for (const room of allowedRooms) {
      if (roomFreeAtSlot(room, cells, slot, cell.id)) continue
      const occ = occupantsAtSlot(cells, slot, room.id, cell.id)
      if (occ.length === 0) continue
      const existing = byId.get(room.id)
      if (existing) {
        existing.allowed = true
        existing.display_name = room.display_name
      } else {
        byId.set(room.id, {
          id: room.id,
          display_name: room.display_name,
          occupants: occ,
          allowed: true,
        })
      }
    }
    return [...byId.values()]
  }, [allowedRooms, cells, cell.id, cell.day_of_week, cell.lesson_number])

  const className = classNameById[cell.class_id] ?? `класс ${cell.class_id}`
  const slotLabel = cell.lesson_number === 0 ? 'классный час' : `урок ${cell.lesson_number}`
  const title = `${className}, ${dayNames[cell.day_of_week - 1]}, ${slotLabel}`

  function save() {
    if (swapWith) {
      if (!confirm(swapConfirmText(cell, swapWith, classNameById))) return
      onSwap(swapWith)
      return
    }
    onChangeClassroom(classroomId === '' ? null : classroomId)
  }

  return (
    <ModalPortal>
      <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,.35)' }}>
        <div className="modal-dialog">
          <div className="modal-content">
            <div className="modal-header">
              <h5 className="modal-title">Изменить кабинет</h5>
              <button type="button" className="btn-close" aria-label="Закрыть" onClick={onClose} />
            </div>
            <div className="modal-body">
              <div className="text-muted small mb-2">{title}</div>
              <div className="mb-3">
                {cell.subject_name}
                {cell.group_number != null ? ` · гр.${cell.group_number}` : ''}
                {cell.teacher_name ? ` · ${cell.teacher_name}` : ''}
              </div>
              {error && (
                <div className="alert alert-danger py-2" style={{ whiteSpace: 'pre-line' }}>
                  <strong>Нельзя сменить кабинет</strong>
                  <div className="mt-1">{error}</div>
                </div>
              )}
              {q.isLoading && <div>Загрузка…</div>}
              {q.isError && <div className="text-danger">{(q.error as Error).message}</div>}
              {q.data && (
                <div className="mb-3">
                  <label className="form-label fw-bold">Кабинет</label>
                  <ClassroomPicker
                    classroomId={classroomId}
                    selectedOccupantId={swapWith?.id ?? null}
                    freeRooms={freeRooms}
                    occupiedRooms={occupiedRooms}
                    classNameById={classNameById}
                    allowSelectOccupied
                    onChangeFree={(id) => {
                      setSwapWith(null)
                      setClassroomId(id)
                    }}
                    onPickOccupied={(occupant) => {
                      setClassroomId(occupant.classroom_id ?? '')
                      setSwapWith(occupant)
                    }}
                  />
                </div>
              )}
              <WhyPanel
                assignmentId={cell.assignment_id}
                day={cell.day_of_week}
                lesson={cell.lesson_number}
                classroomId={
                  swapWith?.classroom_id ?? (classroomId === '' ? null : classroomId)
                }
                cellId={cell.id}
              />
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                Отмена
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={submitting || q.isLoading}
                onClick={save}
              >
                {submitting ? 'Сохранение…' : swapWith ? 'Поменять местами' : 'Сохранить'}
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
    <div className="why-panel border rounded p-2 small">
      <div className="why-panel-title fw-semibold mb-1">Почему</div>
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
              <div className="why-panel-muted">Другие свободные слоты:</div>
              <ul className="why-panel-list mb-0 mt-1 ps-3">
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
