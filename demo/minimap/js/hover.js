function teacherFromEvent(target) {
  if (!(target instanceof Element)) return null
  const el = target.closest('[data-teacher-key]')
  return el && el.dataset.teacherKey ? el.dataset.teacherKey : null
}

function applyTeacherHover(root, key) {
  const prev = root.getAttribute('data-hover-teacher')
  if ((key || '') === (prev || '')) return
  if (key) root.setAttribute('data-hover-teacher', key)
  else root.removeAttribute('data-hover-teacher')
  root.classList.toggle('is-teacher-hover', Boolean(key))
  root.querySelectorAll('[data-teacher-key]').forEach((el) => {
    el.classList.toggle('teacher-highlight', Boolean(key) && el.dataset.teacherKey === key)
  })
}

function bindTeacherHover(root) {
  root.addEventListener('mouseover', (e) => {
    applyTeacherHover(root, teacherFromEvent(e.target))
  })
  root.addEventListener('mouseout', (e) => {
    const next = teacherFromEvent(e.relatedTarget)
    if (next && e.relatedTarget instanceof Node && root.contains(e.relatedTarget)) {
      applyTeacherHover(root, next)
      return
    }
    applyTeacherHover(root, null)
  })
}
