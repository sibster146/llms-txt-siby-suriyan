import type { ReactNode } from 'react'
import { FileText, Globe2, ShieldCheck } from 'lucide-react'
import { Brand } from './Brand'

interface AuthShellProps {
  children: ReactNode
  description: string
  title: string
}

export function AuthShell({ children, description, title }: AuthShellProps) {
  return (
    <main className="auth-layout">
      <section className="context-panel">
        <Brand />
        <div className="context-copy">
          <p className="eyebrow">Built for the generative web</p>
          <h1>Make your website legible to AI.</h1>
          <p>Generate a clear, maintained guide to the pages that matter most.</p>
        </div>
        <div className="context-points" aria-label="Product highlights">
          <span><Globe2 size={18} /> Understand your whole site</span>
          <span><FileText size={18} /> Produce a standards-ready file</span>
          <span><ShieldCheck size={18} /> Keep every revision in one place</span>
        </div>
      </section>

      <section className="form-panel">
        <div className="auth-form-wrap">
          <div className="mobile-brand"><Brand /></div>
          <header className="auth-heading">
            <h2>{title}</h2>
            <p>{description}</p>
          </header>
          {children}
        </div>
      </section>
    </main>
  )
}
