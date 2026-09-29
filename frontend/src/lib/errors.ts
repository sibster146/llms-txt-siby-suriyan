export function authErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) return 'Something went wrong. Please try again.'
  if (error.name === 'NotAuthorizedException') return 'Incorrect email or password.'
  if (error.name === 'UserNotFoundException') return 'No account was found for this email.'
  if (error.name === 'CodeMismatchException') return 'That reset code is not valid.'
  if (error.name === 'ExpiredCodeException') return 'That reset code has expired.'
  return error.message
}
