import { useState } from 'react'
import { Check, FileText, LoaderCircle, LogOut } from 'lucide-react'
import { Brand } from '../components/Brand'
import type { AuthenticatedUser } from '../lib/auth'

interface HomePageProps {
  onSignOut: () => Promise<void>
  user: AuthenticatedUser
}

export function HomePage({ onSignOut, user }: HomePageProps) {
  const [signingOut, setSigningOut] = useState(false)

  async function handleSignOut() {
    setSigningOut(true)
    try {
      await onSignOut()
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <Brand />
        <button className="icon-text-button" disabled={signingOut} onClick={handleSignOut} type="button">
          {signingOut ? <LoaderCircle className="spin" size={17} /> : <LogOut size={17} />}
          Sign out
        </button>
      </header>
      <section className="empty-state">
        <div className="success-mark"><Check size={25} /></div>
        <p className="eyebrow">Account ready</p>
        <h1>Welcome to your workspace.</h1>
        <p className="signed-in-as">Signed in as {user.email}</p>
        <div className="next-task">
          <FileText size={20} />
          <div>
            <strong>Website analysis comes next</strong>
            <span>Your authentication foundation is connected and working.</span>
          </div>
        </div>
      </section>
    </main>
  )
}
