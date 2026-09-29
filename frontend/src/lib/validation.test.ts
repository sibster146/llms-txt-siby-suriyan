import { describe, expect, it } from 'vitest'
import { passwordIssues, passwordRequirements } from './validation'

describe('passwordIssues', () => {
  it('accepts a password matching the Cognito policy', () => {
    expect(passwordIssues('StrongPassword1!')).toEqual([])
  })

  it('describes missing requirements', () => {
    expect(passwordIssues('short')).toEqual([
      'at least 12 characters',
      'one uppercase letter',
      'one number',
      'one symbol',
    ])
  })

  it('updates each requirement independently', () => {
    expect(passwordRequirements('Password123').map(({ id, isMet }) => ({ id, isMet }))).toEqual([
      { id: 'length', isMet: false },
      { id: 'lowercase', isMet: true },
      { id: 'uppercase', isMet: true },
      { id: 'number', isMet: true },
      { id: 'symbol', isMet: false },
    ])
  })
})
