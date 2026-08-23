import { useId } from 'react'

type BrandMarkProps = {
  className?: string
  size?: number
}

export function BrandMark({ className = '', size = 38 }: BrandMarkProps) {
  const uid = useId().replace(/:/g, '')
  const gid = `mark-${uid}`
  return (
    <span className={`brand-mark ${className}`.trim()} aria-hidden>
      <svg viewBox="0 0 38 38" width={size} height={size} role="img">
        <defs>
          <linearGradient id={gid} x1="8" y1="4" x2="32" y2="34">
            <stop stopColor="#2EC4B6" />
            <stop offset="1" stopColor="#147F78" />
          </linearGradient>
        </defs>
        <rect width="38" height="38" rx="11" fill={`url(#${gid})`} />
        <rect x="7" y="7" width="24" height="24" rx="6" fill="#EEF3EA" />
        <rect x="9.5" y="9.5" width="8" height="8" rx="2.2" fill="#147F78" />
        <rect x="20.5" y="9.5" width="8" height="8" rx="2.2" fill="#E0A45A" />
        <rect x="9.5" y="20.5" width="8" height="8" rx="2.2" fill="#0B4A46" />
        <rect x="20.5" y="20.5" width="8" height="8" rx="2.2" fill="#E07A5F" />
      </svg>
    </span>
  )
}
