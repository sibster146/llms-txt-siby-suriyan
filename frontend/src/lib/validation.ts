export function passwordIssues(password: string): string[] {
  const issues: string[] = []
  if (password.length < 12) issues.push('12 characters')
  if (!/[a-z]/.test(password)) issues.push('a lowercase letter')
  if (!/[A-Z]/.test(password)) issues.push('an uppercase letter')
  if (!/\d/.test(password)) issues.push('a number')
  if (!/[^A-Za-z0-9]/.test(password)) issues.push('a symbol')
  return issues
}
