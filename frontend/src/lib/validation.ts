export interface PasswordRequirement {
  id: string
  label: string
  isMet: boolean
}

export function passwordRequirements(password: string): PasswordRequirement[] {
  return [
    { id: 'length', label: 'At least 12 characters', isMet: password.length >= 12 },
    { id: 'lowercase', label: 'One lowercase letter', isMet: /[a-z]/.test(password) },
    { id: 'uppercase', label: 'One uppercase letter', isMet: /[A-Z]/.test(password) },
    { id: 'number', label: 'One number', isMet: /\d/.test(password) },
    { id: 'symbol', label: 'One symbol', isMet: /[^A-Za-z0-9]/.test(password) },
  ]
}

export function passwordIssues(password: string): string[] {
  return passwordRequirements(password)
    .filter((requirement) => !requirement.isMet)
    .map((requirement) => requirement.label.toLowerCase())
}
