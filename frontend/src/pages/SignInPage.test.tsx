import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SignInPage } from './SignInPage'

const authMocks = vi.hoisted(() => ({
  authenticateGuest: vi.fn(),
}))

vi.mock('../lib/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/auth')>()
  return {
    ...actual,
    authenticateGuest: authMocks.authenticateGuest,
  }
})

describe('SignInPage', () => {
  beforeEach(() => {
    authMocks.authenticateGuest.mockReset()
  })

  it('starts a guest session from the button below sign in', async () => {
    const onSignedIn = vi.fn()
    authMocks.authenticateGuest.mockResolvedValue({
      id: 'guest-123',
      email: 'guest@example.com',
    })

    render(
      <SignInPage
        isConfigured
        notice=""
        onForgotPassword={vi.fn()}
        onNavigateToSignUp={vi.fn()}
        onSignedIn={onSignedIn}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Continue as a Guest' }))

    await waitFor(() => {
      expect(authMocks.authenticateGuest).toHaveBeenCalledOnce()
      expect(onSignedIn).toHaveBeenCalledWith({
        id: 'guest-123',
        email: 'guest@example.com',
      })
    })
  })
})
