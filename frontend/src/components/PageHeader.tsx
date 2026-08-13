import type { ReactNode } from 'react'

type Props = {
  title: string
  subtitle?: string
  actions?: ReactNode
}

export function PageHeader({ title, subtitle, actions }: Props) {
  return (
    <div className="page-header d-flex flex-wrap justify-content-between align-items-start gap-2">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions ? <div className="d-flex flex-wrap gap-2 align-items-center">{actions}</div> : null}
    </div>
  )
}
