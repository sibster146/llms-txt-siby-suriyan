const apiUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

interface ApiError {
  detail?: string
}

export async function createAccount(email: string, password: string): Promise<void> {
  const response = await fetch(`${apiUrl}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiError
    throw new Error(body.detail || 'Unable to create your account.')
  }
}
