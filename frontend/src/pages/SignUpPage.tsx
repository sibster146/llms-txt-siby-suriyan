import { type FormEvent, useState } from 'react'
import { ArrowRight, LoaderCircle, LockKeyhole, Mail } from 'lucide-react'
import { AuthShell } from '../components/AuthShell'
import { PasswordChecklist } from '../components/PasswordChecklist'
import { createAccount } from '../lib/api'
import { type AuthenticatedUser, authenticate } from '../lib/auth'
import { authErrorMessage } from '../lib/errors'
import { passwordIssues, passwordRequirements } from '../lib/validation'

interface SignUpPageProps {
  isConfigured: boolean
  onNavigateToSignIn: () => void
  onSignedIn: (user: AuthenticatedUser) => void
}

export function SignUpPage({ isConfigured, onNavigateToSignIn, onSignedIn }: SignUpPageProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const passwordsMatch = confirmPassword.length > 0 && password === confirmPassword
  const passwordIsReady = passwordRequirements(password).every(({ isMet }) => isMet) && passwordsMatch

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    if (!isConfigured) {
      setError('Add the Cognito IDs to frontend/.env before using authentication.')
      return
    }

    setSubmitting(true)
    try {
      const issues = passwordIssues(password)
      if (issues.length) throw new Error(`Password needs ${issues.join(', ')}.`)
      if (!passwordsMatch) throw new Error('Passwords do not match.')
      const normalizedEmail = email.trim().toLowerCase()
      await createAccount(normalizedEmail, password)
      onSignedIn(await authenticate(normalizedEmail, password))
    } catch (caughtError) {
      setError(authErrorMessage(caughtError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell title="Create your account" description="Start with your email and a secure password.">
      <div className="segment-control" aria-label="Account action">
        <button onClick={onNavigateToSignIn} type="button">Sign in</button>
        <button className="active" type="button">Create account</button>
      </div>
      <form onSubmit={handleSubmit}>
        <label htmlFor="email">Email</label>
        <div className="input-wrap">
          <Mail aria-hidden="true" size={18} />
          <input autoComplete="email" id="email" onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" required type="email" value={email} />
        </div>
        <label htmlFor="password">Password</label>
        <div className="input-wrap">
          <LockKeyhole aria-hidden="true" size={18} />
          <input autoComplete="new-password" id="password" maxLength={256} minLength={12} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
        </div>
        <label htmlFor="confirm-password">Confirm password</label>
        <div className="input-wrap">
          <LockKeyhole aria-hidden="true" size={18} />
          <input autoComplete="new-password" id="confirm-password" maxLength={256} minLength={12} onChange={(event) => setConfirmPassword(event.target.value)} required type="password" value={confirmPassword} />
        </div>
        <PasswordChecklist confirmPassword={confirmPassword} password={password} />
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary-button" disabled={submitting || !passwordIsReady} type="submit">
          {submitting ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}
          Create account
        </button>
      </form>
    </AuthShell>
  )
}
