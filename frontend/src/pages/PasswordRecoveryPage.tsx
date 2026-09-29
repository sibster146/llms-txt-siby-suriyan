import { type FormEvent, useState } from 'react'
import { ArrowRight, LoaderCircle, LockKeyhole, Mail, ShieldCheck } from 'lucide-react'
import { AuthShell } from '../components/AuthShell'
import { PasswordChecklist } from '../components/PasswordChecklist'
import { finishPasswordReset, startPasswordReset } from '../lib/auth'
import { authErrorMessage } from '../lib/errors'
import { passwordIssues, passwordRequirements } from '../lib/validation'

type RecoveryStep = 'request-code' | 'reset-password'

interface PasswordRecoveryPageProps {
  isConfigured: boolean
  onBackToSignIn: () => void
  onPasswordReset: () => void
}

export function PasswordRecoveryPage({ isConfigured, onBackToSignIn, onPasswordReset }: PasswordRecoveryPageProps) {
  const [step, setStep] = useState<RecoveryStep>('request-code')
  const [email, setEmail] = useState('')
  const [resetCode, setResetCode] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const passwordsMatch = confirmPassword.length > 0 && password === confirmPassword
  const passwordIsReady = passwordRequirements(password).every(({ isMet }) => isMet) && passwordsMatch
  const isResetStep = step === 'reset-password'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setNotice('')
    if (!isConfigured) {
      setError('Add the Cognito IDs to frontend/.env before using authentication.')
      return
    }

    setSubmitting(true)
    try {
      const normalizedEmail = email.trim().toLowerCase()
      if (!isResetStep) {
        await startPasswordReset(normalizedEmail)
        setStep('reset-password')
        setNotice('We sent a reset code to your email.')
        return
      }

      const issues = passwordIssues(password)
      if (issues.length) throw new Error(`Password needs ${issues.join(', ')}.`)
      if (!passwordsMatch) throw new Error('Passwords do not match.')
      await finishPasswordReset(normalizedEmail, resetCode, password)
      onPasswordReset()
    } catch (caughtError) {
      setError(authErrorMessage(caughtError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      title={isResetStep ? 'Check your inbox' : 'Reset your password'}
      description={isResetStep ? 'Enter the code and choose a new password.' : 'We will send a reset code to your email.'}
    >
      <form onSubmit={handleSubmit}>
        <label htmlFor="email">Email</label>
        <div className="input-wrap">
          <Mail aria-hidden="true" size={18} />
          <input autoComplete="email" disabled={isResetStep} id="email" onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" required type="email" value={email} />
        </div>
        {isResetStep && (
          <>
            <label htmlFor="reset-code">Reset code</label>
            <div className="input-wrap">
              <ShieldCheck aria-hidden="true" size={18} />
              <input autoComplete="one-time-code" id="reset-code" inputMode="numeric" onChange={(event) => setResetCode(event.target.value)} placeholder="Enter the code" required value={resetCode} />
            </div>
            <label htmlFor="password">New password</label>
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
          </>
        )}
        {notice && <p className="notice" role="status">{notice}</p>}
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary-button" disabled={submitting || (isResetStep && !passwordIsReady)} type="submit">
          {submitting ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}
          {isResetStep ? 'Update password' : 'Send reset code'}
        </button>
      </form>
      <button className="back-button" onClick={onBackToSignIn} type="button">Back to sign in</button>
    </AuthShell>
  )
}
