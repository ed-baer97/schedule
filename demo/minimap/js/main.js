;(function boot() {
  const card = document.getElementById('grid-card')
  bindTeacherHover(card)
  bindMinimap({
    mapEl: document.getElementById('minimap-map'),
    viewEl: document.getElementById('minimap-view'),
    viewport: document.getElementById('viewport'),
    hideBtn: document.getElementById('minimap-hide'),
    fabBtn: document.getElementById('minimap-fab'),
    minimapEl: document.getElementById('minimap'),
  })
})()
