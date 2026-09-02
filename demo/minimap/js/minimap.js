function readView(el) {
  return {
    sl: el.scrollLeft,
    st: el.scrollTop,
    sw: Math.max(1, el.scrollWidth),
    sh: Math.max(1, el.scrollHeight),
    cw: Math.max(1, el.clientWidth),
    ch: Math.max(1, el.clientHeight),
  }
}

function clampScroll(el, left, top) {
  el.scrollLeft = Math.max(0, Math.min(left, el.scrollWidth - el.clientWidth))
  el.scrollTop = Math.max(0, Math.min(top, el.scrollHeight - el.clientHeight))
}

function scrollSlot(viewport, id) {
  const target = document.getElementById(id)
  if (!target) return
  const sticky = viewport.querySelector('thead')
  const offsetY = (sticky ? sticky.getBoundingClientRect().height : 0) + 4
  const lessonCol = viewport.querySelector('tbody td')
  const offsetX = (lessonCol ? lessonCol.getBoundingClientRect().width : 80) + 4
  const t = target.getBoundingClientRect()
  const v = viewport.getBoundingClientRect()
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

function bindMinimap(opts) {
  const { mapEl, viewEl, viewport, hideBtn, fabBtn, minimapEl } = opts
  let drag = null

  function syncView() {
    const v = readView(viewport)
    viewEl.style.left = `${(v.sl / v.sw) * 100}%`
    viewEl.style.top = `${(v.st / v.sh) * 100}%`
    viewEl.style.width = `${Math.min(100, (v.cw / v.sw) * 100)}%`
    viewEl.style.height = `${Math.min(100, (v.ch / v.sh) * 100)}%`
  }

  viewport.addEventListener('scroll', syncView, { passive: true })
  window.addEventListener('resize', syncView)
  syncView()

  mapEl.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return
    e.preventDefault()
    mapEl.setPointerCapture(e.pointerId)
    const rect = mapEl.getBoundingClientRect()
    const v = readView(viewport)
    const localX = e.clientX - rect.left
    const localY = e.clientY - rect.top
    const viewLeft = (v.sl / v.sw) * rect.width
    const viewTop = (v.st / v.sh) * rect.height
    const viewW = (v.cw / v.sw) * rect.width
    const viewH = (v.ch / v.sh) * rect.height
    const inside =
      localX >= viewLeft &&
      localX <= viewLeft + viewW &&
      localY >= viewTop &&
      localY <= viewTop + viewH
    const hit = e.target.closest('[data-slot-id]')
    const sid = hit && hit.dataset.slotId
    if (!inside && !sid) {
      clampScroll(
        viewport,
        (localX / rect.width) * v.sw - v.cw / 2,
        (localY / rect.height) * v.sh - v.ch / 2,
      )
    }
    drag = {
      startX: e.clientX,
      startY: e.clientY,
      startSl: viewport.scrollLeft,
      startSt: viewport.scrollTop,
      mapW: rect.width,
      mapH: rect.height,
      moved: false,
      slotId: sid || null,
    }
  })

  mapEl.addEventListener('pointermove', (e) => {
    if (!drag) return
    const dx = e.clientX - drag.startX
    const dy = e.clientY - drag.startY
    if (!drag.moved && Math.abs(dx) < 3 && Math.abs(dy) < 3) return
    drag.moved = true
    clampScroll(
      viewport,
      drag.startSl + (dx / drag.mapW) * viewport.scrollWidth,
      drag.startSt + (dy / drag.mapH) * viewport.scrollHeight,
    )
  })

  function endDrag(e) {
    const current = drag
    drag = null
    try {
      mapEl.releasePointerCapture(e.pointerId)
    } catch (_) {
      /* ignore */
    }
    if (!current || current.moved) return
    if (current.slotId) scrollSlot(viewport, current.slotId)
  }

  mapEl.addEventListener('pointerup', endDrag)
  mapEl.addEventListener('pointercancel', endDrag)
  mapEl.addEventListener(
    'wheel',
    (e) => {
      viewport.scrollTop += e.deltaY
      viewport.scrollLeft += e.deltaX
      e.preventDefault()
    },
    { passive: false },
  )

  hideBtn.addEventListener('click', () => {
    minimapEl.hidden = true
    fabBtn.hidden = false
  })
  fabBtn.addEventListener('click', () => {
    minimapEl.hidden = false
    fabBtn.hidden = true
    syncView()
  })
}
