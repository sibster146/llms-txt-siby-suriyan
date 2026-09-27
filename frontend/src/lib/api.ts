import { getAccessToken } from './auth'

const apiUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

interface ApiError {
  detail?: string
}

export type CrawlStatus = 'PENDING' | 'WORKING' | 'CRAWLED' | 'COMPLETED' | 'FAILED'

export interface CreateCrawlResponse {
  site_id: string
  crawl_run_id: string
  url: string
  status: 'PENDING'
}

export interface CrawlStatusResponse {
  site_id: string
  crawl_run_id: string
  status: CrawlStatus
  pending_page_count: number
  discovered_page_count: number
  completed_page_count: number
  failed_page_count: number
  created_at: string
  updated_at: string | null
}

export interface SiteSummary {
  site_id: string
  root_url: string
  last_crawl_run_id: string
  created_at: string
  updated_at: string
  modified_at: string | null
}

async function errorMessage(response: Response, fallback: string): Promise<string> {
  const body = (await response.json().catch(() => ({}))) as ApiError
  return typeof body.detail === 'string' ? body.detail : fallback
}

async function authorizationHeaders(): Promise<Record<string, string>> {
  return { Authorization: `Bearer ${await getAccessToken()}` }
}

export async function createAccount(email: string, password: string): Promise<void> {
  const response = await fetch(`${apiUrl}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Unable to create your account.'))
  }
}

export async function createCrawl(url: string): Promise<CreateCrawlResponse> {
  const response = await fetch(`${apiUrl}/llms-txt`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(await authorizationHeaders()),
    },
    body: JSON.stringify({ url }),
  })

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Unable to create the crawl.'))
  }
  return response.json() as Promise<CreateCrawlResponse>
}

export async function listSites(): Promise<SiteSummary[]> {
  const response = await fetch(`${apiUrl}/llms-txt/sites`, {
    headers: await authorizationHeaders(),
  })

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Unable to load your websites.'))
  }
  return response.json() as Promise<SiteSummary[]>
}

export async function getCrawlStatus(
  siteId: string,
  crawlRunId: string,
): Promise<CrawlStatusResponse> {
  const response = await fetch(
    `${apiUrl}/llms-txt/${encodeURIComponent(siteId)}/crawls/${encodeURIComponent(crawlRunId)}`,
    { headers: await authorizationHeaders() },
  )

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Unable to load the crawl status.'))
  }
  return response.json() as Promise<CrawlStatusResponse>
}
