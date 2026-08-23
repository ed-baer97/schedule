export type ThemeName = 'light' | 'dark'

const KEY = 'kivi-theme'

export function getStoredTheme(): ThemeName {
  try {
    const value = localStorage.getItem(KEY)
    if (value === 'dark' || value === 'light') return value
  } catch {
    /* ignore */
  }
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark'
  }
  return 'light'
}

export function applyTheme(theme: ThemeName) {
  document.documentElement.dataset.theme = theme
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    /* ignore */
  }
}

export function initTheme() {
  applyTheme(getStoredTheme())
}
