import { type FormEvent, useEffect, useState } from 'react'
import {
  ArrowRight,
  Check,
  FileText,
  Globe2,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Mail,
  ShieldCheck,
} from 'lucide-react'
import { createAccount } from './lib/api'
import {
  type AuthenticatedUser,
  authenticate,
  currentUser,
  endSession,
  finishPasswordReset,
  startPasswordReset,
} from './lib/auth'
import { passwordIssues } from './lib/validation'

type AuthView = 'sign-in' | 'sign-up' | 'forgot-password' | 'reset-password'

interface AppProps {
  isConfigured: boolean
}

function errorMessage(error: unknown): string {
  if (!(error instanceof Error)) return 'Something went wrong. Please try again.'
  if (error.name === 'NotAuthorizedException') return 'Incorrect email or password.'
  if (error.name === 'UserNotFoundException') return 'No account was found for this email.'
  if (error.name === 'CodeMismatchException') return 'That reset code is not valid.'
  if (error.name === 'ExpiredCodeException') return 'That reset code has expired.'
  return error.message
}

export function App({ isConfigured }: AppProps) {
  const [view, setView] = useState<AuthView>('sign-in')
  const [user, setUser] = useState<AuthenticatedUser | null>(null)
  const [checkingSession, setCheckingSession] = useState(isConfigured)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [resetCode, setResetCode] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!isConfigured) return
    currentUser().then(setUser).finally(() => setCheckingSession(false))
  }, [isConfigured])

  function changeView(nextView: AuthView) {
    setView(nextView)
    setError('')
    setNotice('')
    setPassword('')
    setConfirmPassword('')
    setResetCode('')
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setNotice('')

    if (!isConfigured) {
      setError('Add the Cognito IDs to frontend/.env before using authentication.')
      return
    }

    const normalizedEmail = email.trim().toLowerCase()
    setSubmitting(true)

    try {
      if (view === 'sign-up') {
        const issues = passwordIssues(password)
        if (issues.length) throw new Error(`Password needs ${issues.join(', ')}.`)
        if (password !== confirmPassword) throw new Error('Passwords do not match.')
        await createAccount(normalizedEmail, password)
        setUser(await authenticate(normalizedEmail, password))
      } else if (view === 'sign-in') {
        setUser(await authenticate(normalizedEmail, password))
      } else if (view === 'forgot-password') {
        await startPasswordReset(normalizedEmail)
        setView('reset-password')
        setNotice('We sent a reset code to your email.')
      } else {
        const issues = passwordIssues(password)
        if (issues.length) throw new Error(`Password needs ${issues.join(', ')}.`)
        if (password !== confirmPassword) throw new Error('Passwords do not match.')
        await finishPasswordReset(normalizedEmail, resetCode, password)
        setPassword('')
        setConfirmPassword('')
        setResetCode('')
        setView('sign-in')
        setNotice('Password updated. You can sign in now.')
      }
    } catch (caughtError) {
      setError(errorMessage(caughtError))
    } finally {
      setSubmitting(false)
    }
  }

  async function handleSignOut() {
    setSubmitting(true)
    try {
      await endSession()
      setUser(null)
      setView('sign-in')
    } finally {
      setSubmitting(false)
    }
  }

  if (checkingSession) {
    return (
      <div className="loading-screen" aria-label="Loading session">
        <LoaderCircle className="spin" size={26} />
      </div>
    )
  }

  if (user) {
    return (
      <main className="app-shell">
        <header className="app-header">
          <Brand />
          <button className="icon-text-button" onClick={handleSignOut} type="button">
            <LogOut size={17} />
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
          <AuthHeading view={view} />

          {(view === 'sign-in' || view === 'sign-up') && (
            <div className="segment-control" aria-label="Account action">
              <button
                className={view === 'sign-in' ? 'active' : ''}
                onClick={() => changeView('sign-in')}
                type="button"
              >
                Sign in
              </button>
              <button
                className={view === 'sign-up' ? 'active' : ''}
                onClick={() => changeView('sign-up')}
                type="button"
              >
                Create account
              </button>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <label htmlFor="email">Email</label>
            <div className="input-wrap">
              <Mail aria-hidden="true" size={18} />
              <input
                autoComplete="email"
                id="email"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@company.com"
                required
                type="email"
                value={email}
              />
            </div>

            {view === 'reset-password' && (
              <>
                <label htmlFor="reset-code">Reset code</label>
                <div className="input-wrap">
                  <ShieldCheck aria-hidden="true" size={18} />
                  <input
                    autoComplete="one-time-code"
                    id="reset-code"
                    inputMode="numeric"
                    onChange={(event) => setResetCode(event.target.value)}
                    placeholder="Enter the code"
                    required
                    value={resetCode}
                  />
                </div>
              </>
            )}

            {view !== 'forgot-password' && (
              <>
                <div className="label-row">
                  <label htmlFor="password">
                    {view === 'reset-password' ? 'New password' : 'Password'}
                  </label>
                  {view === 'sign-in' && (
                    <button className="text-button" onClick={() => changeView('forgot-password')} type="button">
                      Forgot password?
                    </button>
                  )}
                </div>
                <div className="input-wrap">
                  <LockKeyhole aria-hidden="true" size={18} />
                  <input
                    autoComplete={view === 'sign-in' ? 'current-password' : 'new-password'}
                    id="password"
                    minLength={12}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                    type="password"
                    value={password}
                  />
                </div>
              </>
            )}

            {(view === 'sign-up' || view === 'reset-password') && (
              <>
                <label htmlFor="confirm-password">Confirm password</label>
                <div className="input-wrap">
                  <LockKeyhole aria-hidden="true" size={18} />
                  <input
                    autoComplete="new-password"
                    id="confirm-password"
                    minLength={12}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    required
                    type="password"
                    value={confirmPassword}
                  />
                </div>
                <p className="field-hint">12+ characters with upper, lower, number, and symbol.</p>
              </>
            )}

            {notice && <p className="notice" role="status">{notice}</p>}
            {error && <p className="error" role="alert">{error}</p>}

            <button className="primary-button" disabled={submitting} type="submit">
              {submitting ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}
              {submitLabel(view)}
            </button>
          </form>

          {(view === 'forgot-password' || view === 'reset-password') && (
            <button className="back-button" onClick={() => changeView('sign-in')} type="button">
              Back to sign in
            </button>
          )}
        </div>
      </section>
    </main>
  )
}

function Brand() {
  return (
    <a className="brand" href="/" aria-label="llms.txt home">
      <span className="brand-mark"><FileText size={18} /></span>
      llms.txt
    </a>
  )
}

function AuthHeading({ view }: { view: AuthView }) {
  const content = {
    'sign-in': ['Welcome back', 'Sign in to continue to your websites.'],
    'sign-up': ['Create your account', 'Start with your email and a secure password.'],
    'forgot-password': ['Reset your password', 'We will send a reset code to your email.'],
    'reset-password': ['Check your inbox', 'Enter the code and choose a new password.'],
  }[view]

  return (
    <header className="auth-heading">
      <h2>{content[0]}</h2>
      <p>{content[1]}</p>
    </header>
  )
}

function submitLabel(view: AuthView): string {
  return {
    'sign-in': 'Sign in',
    'sign-up': 'Create account',
    'forgot-password': 'Send reset code',
    'reset-password': 'Update password',
  }[view]
}
