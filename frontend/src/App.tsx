import { useEffect, useState } from 'react'
import { LoaderCircle } from 'lucide-react'
import { type AuthenticatedUser, currentUser, endSession } from './lib/auth'
import { HomePage } from './pages/HomePage'
import { PasswordRecoveryPage } from './pages/PasswordRecoveryPage'
import { SignInPage } from './pages/SignInPage'
import { SignUpPage } from './pages/SignUpPage'

type Page = 'sign-in' | 'sign-up' | 'password-recovery'

interface AppProps {
  isConfigured: boolean
}

export function App({ isConfigured }: AppProps) {
  const [page, setPage] = useState<Page>('sign-in')
  const [user, setUser] = useState<AuthenticatedUser | null>(null)
  const [checkingSession, setCheckingSession] = useState(isConfigured)
  const [signInNotice, setSignInNotice] = useState('')

  useEffect(() => {
    if (!isConfigured) return
    currentUser().then(setUser).finally(() => setCheckingSession(false))
  }, [isConfigured])

  function navigate(nextPage: Page) {
    setSignInNotice('')
    setPage(nextPage)
  }

  async function handleSignOut() {
    await endSession()
    setUser(null)
    setPage('sign-in')
  }

  if (checkingSession) {
    return (
      <div className="loading-screen" aria-label="Loading session">
        <LoaderCircle className="spin" size={26} />
      </div>
    )
  }

  if (user) return <HomePage onSignOut={handleSignOut} user={user} />

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
