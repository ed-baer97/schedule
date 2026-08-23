import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'

/** Renders a modal on document.body so shell chrome (sidebar/navbar/glass) cannot cover it. */
export function ModalPortal({ children }: { children: ReactNode }) {
  return createPortal(children, document.body)
}
