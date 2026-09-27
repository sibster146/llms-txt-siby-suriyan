import { describe, expect, it } from 'vitest'
import { passwordIssues } from './validation'

describe('passwordIssues', () => {
  it('accepts a password matching the Cognito policy', () => {
    expect(passwordIssues('StrongPassword1!')).toEqual([])
  })

  it('describes missing requirements', () => {
    expect(passwordIssues('short')).toEqual([
      '12 characters',
      'an uppercase letter',
      'a number',
      'a symbol',
    ])
  })
})
