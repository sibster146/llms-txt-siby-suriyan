import { type FormEvent, useState } from 'react'
import { ArrowRight, LoaderCircle, LockKeyhole, Mail } from 'lucide-react'
import { AuthShell } from '../components/AuthShell'
import { type AuthenticatedUser, authenticate } from '../lib/auth'
import { authErrorMessage } from '../lib/errors'

interface SignInPageProps {
  isConfigured: boolean
  notice: string
  onForgotPassword: () => void
  onNavigateToSignUp: () => void
  onSignedIn: (user: AuthenticatedUser) => void
}

export function SignInPage({
  isConfigured,
  notice,
  onForgotPassword,
  onNavigateToSignUp,
  onSignedIn,
}: SignInPageProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    if (!isConfigured) {
      setError('Add the Cognito IDs to frontend/.env before using authentication.')
      return
    }

    setSubmitting(true)
    try {
      onSignedIn(await authenticate(email, password))
    } catch (caughtError) {
      setError(authErrorMessage(caughtError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell title="Welcome back" description="Sign in to continue to your websites.">
      <div className="segment-control" aria-label="Account action">
        <button className="active" type="button">Sign in</button>
        <button onClick={onNavigateToSignUp} type="button">Create account</button>
      </div>
      <form onSubmit={handleSubmit}>
        <label htmlFor="email">Email</label>
        <div className="input-wrap">
          <Mail aria-hidden="true" size={18} />
          <input autoComplete="email" id="email" onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" required type="email" value={email} />
        </div>
        <div className="label-row">
          <label htmlFor="password">Password</label>
          <button className="text-button" onClick={onForgotPassword} type="button">Forgot password?</button>
        </div>
        <div className="input-wrap">
          <LockKeyhole aria-hidden="true" size={18} />
          <input autoComplete="current-password" id="password" maxLength={256} minLength={12} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
        </div>
        {notice && <p className="notice" role="status">{notice}</p>}
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary-button" disabled={submitting} type="submit">
          {submitting ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}
          Sign in
        </button>
      </form>
    </AuthShell>
  )
}
