import { useEffect, useState } from 'react'
import { LoaderCircle } from 'lucide-react'
import { type AuthenticatedUser, currentUser, endSession } from './lib/auth'
import { HomePage } from './pages/HomePage'
import { LLMTxtPage } from './pages/LLMTxtPage'
import { PasswordRecoveryPage } from './pages/PasswordRecoveryPage'
import { SignInPage } from './pages/SignInPage'
import { SignUpPage } from './pages/SignUpPage'

type Page = 'sign-in' | 'sign-up' | 'password-recovery'

interface AppProps {
  isConfigured: boolean
}

function siteIdFromPath(): string | null {
  const match = window.location.pathname.match(/^\/sites\/([^/]+)\/?$/)
  if (!match) return null
  try {
    return decodeURIComponent(match[1])
  } catch {
    return null
  }
}

export function App({ isConfigured }: AppProps) {
  const [page, setPage] = useState<Page>('sign-in')
  const [user, setUser] = useState<AuthenticatedUser | null>(null)
  const [checkingSession, setCheckingSession] = useState(isConfigured)
  const [signInNotice, setSignInNotice] = useState('')
  const [selectedSiteId, setSelectedSiteId] = useState(siteIdFromPath)

  useEffect(() => {
    if (!isConfigured) return
    currentUser().then(setUser).finally(() => setCheckingSession(false))
  }, [isConfigured])

  useEffect(() => {
    function syncPageFromHistory() {
      setSelectedSiteId(siteIdFromPath())
    }
    window.addEventListener('popstate', syncPageFromHistory)
    return () => window.removeEventListener('popstate', syncPageFromHistory)
  }, [])

  function navigate(nextPage: Page) {
    setSignInNotice('')
    setPage(nextPage)
  }

  async function handleSignOut() {
    await endSession()
    setUser(null)
    setPage('sign-in')
    setSelectedSiteId(null)
    window.history.replaceState({}, '', '/')
  }

  function openSite(siteId: string) {
    window.history.pushState({}, '', `/sites/${encodeURIComponent(siteId)}`)
    setSelectedSiteId(siteId)
  }

  function openHome() {
    window.history.pushState({}, '', '/')
    setSelectedSiteId(null)
  }

  if (checkingSession) {
    return (
      <div className="loading-screen" aria-label="Loading session">
        <LoaderCircle className="spin" size={26} />
      </div>
    )
  }

  if (user && selectedSiteId) {
    return (
      <LLMTxtPage
        key={selectedSiteId}
        onBack={openHome}
        onSignOut={handleSignOut}
        siteId={selectedSiteId}
      />
    )
  }

  if (user) {
    return <HomePage onSelectSite={openSite} onSignOut={handleSignOut} user={user} />
  }

  if (page === 'sign-up') {
    return (
      <SignUpPage
        isConfigured={isConfigured}
        onNavigateToSignIn={() => navigate('sign-in')}
        onSignedIn={setUser}
      />
    )
  }

  if (page === 'password-recovery') {
    return (
      <PasswordRecoveryPage
        isConfigured={isConfigured}
        onBackToSignIn={() => navigate('sign-in')}
        onPasswordReset={() => {
          setSignInNotice('Password updated. You can sign in now.')
          setPage('sign-in')
        }}
      />
    )
  }

  return (
    <SignInPage
      isConfigured={isConfigured}
      notice={signInNotice}
      onForgotPassword={() => navigate('password-recovery')}
      onNavigateToSignUp={() => navigate('sign-up')}
      onSignedIn={setUser}
    />
  )
}
