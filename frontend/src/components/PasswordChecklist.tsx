import { CheckCircle2, Circle } from 'lucide-react'
import { passwordRequirements } from '../lib/validation'

interface PasswordChecklistProps {
  confirmPassword: string
  password: string
}

export function PasswordChecklist({ confirmPassword, password }: PasswordChecklistProps) {
  const requirements = passwordRequirements(password)
  const passwordsMatch = confirmPassword.length > 0 && password === confirmPassword

  return (
    <div className="password-policy" aria-live="polite">
      <p>Password requirements</p>
      <ul>
        {requirements.map((requirement) => (
          <li className={requirement.isMet ? 'met' : ''} key={requirement.id}>
            {requirement.isMet ? <CheckCircle2 size={15} /> : <Circle size={15} />}
            {requirement.label}
          </li>
        ))}
        <li className={passwordsMatch ? 'met' : ''}>
          {passwordsMatch ? <CheckCircle2 size={15} /> : <Circle size={15} />}
          {confirmPassword ? 'Passwords match' : 'Matching confirmation'}
        </li>
      </ul>
    </div>
  )
}
