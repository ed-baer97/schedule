import '../styles/landing.css'
import { LandingTimetable } from './LandingTimetable'

type AtmosphereBgProps = {
  className?: string
}

export function AtmosphereBg({ className = '' }: AtmosphereBgProps) {
  return (
    <div className={`atmosphere-bg ${className}`.trim()} aria-hidden>
      <div className="landing-orbs" />
      <div className="landing-tt-bg">
        <div className="landing-tt-bg-sheet landing-tt-bg-sheet--a">
          <LandingTimetable />
        </div>
        <div className="landing-tt-bg-sheet landing-tt-bg-sheet--b">
          <LandingTimetable />
        </div>
      </div>
      <div className="landing-grid" />
      <div className="landing-veil" />
    </div>
  )
}
