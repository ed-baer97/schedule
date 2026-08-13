import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type UIEvent,
} from 'react'

const BAR = 12

type Metrics = {
  sl: number
  st: number
  sw: number
  sh: number
  cw: number
  ch: number
}

type Props = {
  children: ReactNode
  className?: string
  onScroll?: (e: UIEvent<HTMLDivElement>) => void
  onViewportReady?: (el: HTMLDivElement) => void
}

export function OverlayScrollArea({ children, className = '', onScroll, onViewportReady }: Props) {
  const viewRef = useRef<HTMLDivElement>(null)
  const saved = useRef({ sl: 0, st: 0 })
  const onReadyRef = useRef(onViewportReady)
  const lastSize = useRef({ w: 0, h: 0, sh: 0, sw: 0 })
  const [m, setM] = useState<Metrics>({ sl: 0, st: 0, sw: 0, sh: 0, cw: 0, ch: 0 })
  onReadyRef.current = onViewportReady

  const measure = useCallback(() => {
    const el = viewRef.current
    if (!el) return
    const next = {
      sl: el.scrollLeft,
      st: el.scrollTop,
      sw: el.scrollWidth,
      sh: el.scrollHeight,
      cw: el.clientWidth,
      ch: el.clientHeight,
    }
    setM(next)
    if (next.st > 0 || next.sl > 0) {
      saved.current = { sl: next.sl, st: next.st }
    }
    const sizeChanged =
      next.cw !== lastSize.current.w ||
      next.ch !== lastSize.current.h ||
      next.sh !== lastSize.current.sh ||
      next.sw !== lastSize.current.sw
    if (sizeChanged) {
      lastSize.current = { w: next.cw, h: next.ch, sh: next.sh, sw: next.sw }
      if (next.ch > 0 && next.sh > 0) onReadyRef.current?.(el)
    }
  }, [])

  useLayoutEffect(() => {
    const el = viewRef.current
    if (!el) return
    if (
      (saved.current.st > 0 || saved.current.sl > 0) &&
      el.scrollTop === 0 &&
      el.scrollLeft === 0
    ) {
      // #region agent log
      fetch('http://127.0.0.1:7749/ingest/55d6f9a3-7152-4cf5-827c-1203474325d2', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '1126ac' },
        body: JSON.stringify({
          sessionId: '1126ac',
          runId: 'pre-fix',
          hypothesisId: 'E',
          location: 'OverlayScrollArea.tsx:useLayoutEffect',
          message: 'restoring zeroed scroll',
          data: { saved: saved.current, ch: el.clientHeight, sh: el.scrollHeight },
          timestamp: Date.now(),
        }),
      }).catch(() => {})
      // #endregion
      el.scrollLeft = saved.current.sl
      el.scrollTop = saved.current.st
    }
  })

  useEffect(() => {
    const el = viewRef.current
    if (!el) return
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    const inner = el.firstElementChild
    if (inner) ro.observe(inner)
    el.addEventListener('scroll', measure, { passive: true })
    window.addEventListener('resize', measure)
    return () => {
      ro.disconnect()
      el.removeEventListener('scroll', measure)
      window.removeEventListener('resize', measure)
    }
  }, [measure])

  function handleScroll(e: UIEvent<HTMLDivElement>) {
    const el = viewRef.current
    if (el) saved.current = { sl: el.scrollLeft, st: el.scrollTop }
    onScroll?.(e)
  }

  const needX = m.sw > m.cw + 1
  const needY = m.sh > m.ch + 1
  const hTrack = Math.max(0, m.cw - (needY ? BAR : 0))
  const vTrack = Math.max(0, m.ch - (needX ? BAR : 0))
  const hThumb = needX && m.sw > 0 ? Math.max(32, (m.cw / m.sw) * hTrack) : 0
  const vThumb = needY && m.sh > 0 ? Math.max(32, (m.ch / m.sh) * vTrack) : 0
  const hMax = Math.max(0, m.sw - m.cw)
  const vMax = Math.max(0, m.sh - m.ch)
  const hLeft = hMax > 0 ? (m.sl / hMax) * (hTrack - hThumb) : 0
  const vTop = vMax > 0 ? (m.st / vMax) * (vTrack - vThumb) : 0

  function startDrag(axis: 'x' | 'y', e: ReactPointerEvent<HTMLElement>) {
    e.preventDefault()
    e.stopPropagation()
    const el = viewRef.current
    if (!el) return
    const startPtr = axis === 'x' ? e.clientX : e.clientY
    const startScroll = axis === 'x' ? el.scrollLeft : el.scrollTop
    const track = axis === 'x' ? hTrack : vTrack
    const thumb = axis === 'x' ? hThumb : vThumb
    const max = axis === 'x' ? hMax : vMax
    const range = track - thumb

    const move = (ev: PointerEvent) => {
      const delta = (axis === 'x' ? ev.clientX : ev.clientY) - startPtr
      const next = startScroll + (range > 0 ? (delta / range) * max : 0)
      if (axis === 'x') el.scrollLeft = next
      else el.scrollTop = next
    }
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  function onTrackDown(axis: 'x' | 'y', e: ReactPointerEvent<HTMLDivElement>) {
    if ((e.target as HTMLElement).closest('.overlay-scroll-thumb')) return
    const el = viewRef.current
    if (!el) return
    const rect = e.currentTarget.getBoundingClientRect()
    if (axis === 'x') {
      const x = e.clientX - rect.left - hThumb / 2
      el.scrollLeft = rect.width > hThumb ? (x / (rect.width - hThumb)) * hMax : 0
    } else {
      const y = e.clientY - rect.top - vThumb / 2
      el.scrollTop = rect.height > vThumb ? (y / (rect.height - vThumb)) * vMax : 0
    }
  }

  return (
    <div className={`overlay-scroll${needX ? ' has-x' : ''}${needY ? ' has-y' : ''} ${className}`.trim()}>
      <div className="overlay-scroll-viewport" ref={viewRef} onScroll={handleScroll}>
        {children}
      </div>
      {needY ? (
        <div className="overlay-scroll-bar overlay-scroll-bar-v" aria-hidden onPointerDown={(e) => onTrackDown('y', e)}>
          <div
            className="overlay-scroll-thumb"
            style={{ height: vThumb, transform: `translateY(${vTop}px)` }}
            onPointerDown={(e) => startDrag('y', e)}
          />
        </div>
      ) : null}
      {needX ? (
        <div className="overlay-scroll-bar overlay-scroll-bar-h" aria-hidden onPointerDown={(e) => onTrackDown('x', e)}>
          <div
            className="overlay-scroll-thumb"
            style={{ width: hThumb, transform: `translateX(${hLeft}px)` }}
            onPointerDown={(e) => startDrag('x', e)}
          />
        </div>
      ) : null}
    </div>
  )
}
