import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { AtmosphereBg } from './AtmosphereBg'
import { BrandMark } from './BrandMark'
import { OverlayScrollArea } from './OverlayScrollArea'
import { ThemeToggle } from './ThemeToggle'

type PublicLayoutProps = {
  children: ReactNode
  active?: 'login'
}

export function PublicLayout({ children, active }: PublicLayoutProps) {
  return (
    <div className="landing-page">
      <AtmosphereBg className="landing-bg" />
      <OverlayScrollArea className="landing-scroll">
        <div className="landing-inner">
          <header className="landing-nav-bar">
            <div className="landing-nav">
              <Link to="/login" className="landing-brand">
                <BrandMark className="landing-mark" size={38} />
                <span className="landing-wordmark">KiVi</span>
              </Link>
              <nav className="landing-nav-links">
                <a href="/login#features">Возможности</a>
                <ThemeToggle variant="landing" />
                <a
                  href="/login#login"
                  className={`landing-nav-cta${active === 'login' ? ' is-active' : ''}`}
                >
                  Войти
                </a>
              </nav>
            </div>
          </header>
          {children}
          <footer className="landing-footer">
            <span>Для завуча и администратора школы</span>
            <span>Учителя · кабинеты · смены · автосборка</span>
          </footer>
        </div>
      </OverlayScrollArea>
    </div>
  )
}
