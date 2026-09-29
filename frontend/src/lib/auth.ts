import { Amplify } from 'aws-amplify'
import { decodeJWT } from '@aws-amplify/core'
import {
  confirmResetPassword,
  fetchAuthSession,
  getCurrentUser,
  resetPassword,
  signIn,
  signOut,
} from 'aws-amplify/auth'
import { cognitoUserPoolsTokenProvider } from 'aws-amplify/auth/cognito'
import { defaultStorage } from 'aws-amplify/utils'
import { apiUrl } from './config'

const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID
const userPoolClientId = import.meta.env.VITE_COGNITO_USER_POOL_CLIENT_ID

interface GuestSessionResponse {
  email: string
  access_token: string
  id_token: string
  refresh_token: string
}

export interface AuthenticatedUser {
  id: string
  email: string
}

async function authError(response: Response): Promise<Error> {
  const body = await response.json().catch(() => ({})) as { detail?: unknown }
  const message = typeof body.detail === 'string' ? body.detail : 'Guest access is unavailable.'
  return new Error(message)
}

export function configureAuth(): boolean {
  if (!userPoolId || !userPoolClientId) {
    return false
  }

  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId,
        userPoolClientId,
        loginWith: { email: true },
      },
    },
  })
  cognitoUserPoolsTokenProvider.setKeyValueStorage(defaultStorage)

  return true
}

export async function currentUser(): Promise<AuthenticatedUser | null> {
  try {
    const session = await fetchAuthSession()
    if (!session.tokens?.accessToken) return null
    const user = await getCurrentUser()
    return {
      id: user.userId,
      email: user.signInDetails?.loginId || user.username,
    }
  } catch {
    return null
  }
}

export async function authenticate(email: string, password: string): Promise<AuthenticatedUser> {
  const result = await signIn({
    username: email.trim().toLowerCase(),
    password,
    options: { authFlowType: 'USER_SRP_AUTH' },
  })

  if (!result.isSignedIn) {
    throw new Error(`Additional sign-in step required: ${result.nextStep.signInStep}`)
  }

  const user = await currentUser()
  if (!user) {
    throw new Error('Sign-in succeeded, but the session could not be loaded.')
  }
  return user
}

export async function authenticateGuest(): Promise<AuthenticatedUser> {
  const response = await fetch(`${apiUrl}/auth/guest`, { method: 'POST' })
  if (!response.ok) throw await authError(response)

  const result = await response.json() as GuestSessionResponse
  const accessToken = decodeJWT(result.access_token)
  const idToken = decodeJWT(result.id_token)
  const username = idToken.payload['cognito:username']
  const issuedAt = accessToken.payload.iat ?? 0

  await cognitoUserPoolsTokenProvider.tokenOrchestrator.clearTokens()
  await cognitoUserPoolsTokenProvider.tokenOrchestrator.setTokens({
    tokens: {
      accessToken,
      idToken,
      refreshToken: result.refresh_token,
      username: typeof username === 'string' ? username : result.email,
      clockDrift: issuedAt * 1000 - Date.now(),
    },
  })

  const user = await currentUser()
  if (!user) {
    throw new Error('Guest sign-in succeeded, but the session could not be loaded.')
  }
  return user
}

export async function endSession(): Promise<void> {
  await signOut()
}

export async function getAccessToken(forceRefresh = false): Promise<string> {
  const session = await fetchAuthSession({ forceRefresh })
  const accessToken = session.tokens?.accessToken
  if (!accessToken) {
    throw new Error('Your session has expired. Sign in again.')
  }
  return accessToken.toString()
}

export async function startPasswordReset(email: string): Promise<void> {
  const result = await resetPassword({ username: email.trim().toLowerCase() })
  if (result.nextStep.resetPasswordStep !== 'CONFIRM_RESET_PASSWORD_WITH_CODE') {
    throw new Error('Password reset is not available for this account.')
  }
}

export async function finishPasswordReset(
  email: string,
  code: string,
  newPassword: string,
): Promise<void> {
  await confirmResetPassword({
    username: email.trim().toLowerCase(),
    confirmationCode: code.trim(),
    newPassword,
  })
}
