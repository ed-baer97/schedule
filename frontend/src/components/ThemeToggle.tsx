import { useEffect, useState } from 'react'
import { applyTheme, getStoredTheme, type ThemeName } from '../theme'

export function ThemeToggle({ variant = 'app' }: { variant?: 'app' | 'landing' }) {
  const [theme, setTheme] = useState<ThemeName>('light')

  useEffect(() => {
    setTheme(getStoredTheme())
  }, [])

  function toggle() {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    applyTheme(next)
  }

  const landing = variant === 'landing'
  return (
    <button
      type="button"
      className={
        landing
          ? 'landing-theme-btn'
          : 'btn btn-sm btn-outline-light'
      }
      onClick={toggle}
      title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
      aria-label={theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'}
    >
      <i className={`bi ${theme === 'dark' ? 'bi-sun' : 'bi-moon'}`} />
    </button>
  )
}
