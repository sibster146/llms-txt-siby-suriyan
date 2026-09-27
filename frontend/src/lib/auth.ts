import { Amplify } from 'aws-amplify'
import {
  confirmResetPassword,
  getCurrentUser,
  resetPassword,
  signIn,
  signOut,
} from 'aws-amplify/auth'

const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID
const userPoolClientId = import.meta.env.VITE_COGNITO_USER_POOL_CLIENT_ID

export interface AuthenticatedUser {
  id: string
  email: string
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

  return true
}

export async function currentUser(): Promise<AuthenticatedUser | null> {
  try {
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

export async function endSession(): Promise<void> {
  await signOut()
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
