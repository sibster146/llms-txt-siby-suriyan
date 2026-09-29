import { getAccessToken } from './auth'

const apiUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

interface ApiError {
  detail?: string
}

export type CrawlStatus =
  | 'PENDING'
  | 'CRAWLING_AND_PARSING'
  | 'GENERATING'
  | 'COMPLETED'
  | 'FAILED'

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
  latest_crawl: CrawlStatusResponse | null
}

export interface LlmsTxtVersionSummary {
  site_id: string
  version_id: string
  crawl_run_id: string
  generated_at: string
  content_hash: string
  status: string
  generation_method: string | null
  model_id: string | null
}

export interface LlmsTxtVersion extends LlmsTxtVersionSummary {
  content: string
}

export interface SiteDetail {
  site_id: string
  root_url: string
  created_at: string
  updated_at: string
  modified_at: string | null
  current_version: LlmsTxtVersion | null
  versions: LlmsTxtVersionSummary[]
}

async function errorMessage(response: Response, fallback: string): Promise<string> {
  const body = (await response.json().catch(() => ({}))) as ApiError
  return typeof body.detail === 'string' ? body.detail : fallback
}

async function authenticatedFetch(input: string, init: RequestInit = {}): Promise<Response> {
  async function send(forceRefresh: boolean): Promise<Response> {
    const headers = new Headers(init.headers)
    headers.set('Authorization', `Bearer ${await getAccessToken(forceRefresh)}`)
    return fetch(input, { ...init, headers })
  }

  const response = await send(false)
  return response.status === 401 ? send(true) : response
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
  const response = await authenticatedFetch(`${apiUrl}/llms-txt`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ url }),
  })

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Unable to create the crawl.'))
  }
  return response.json() as Promise<CreateCrawlResponse>
}

export async function listSites(): Promise<SiteSummary[]> {
  const response = await authenticatedFetch(`${apiUrl}/llms-txt/sites`)

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Unable to load your websites.'))
  }
  return response.json() as Promise<SiteSummary[]>
}

export async function getCrawlStatus(
  siteId: string,
  crawlRunId: string,
): Promise<CrawlStatusResponse> {
  const response = await authenticatedFetch(
    `${apiUrl}/llms-txt/${encodeURIComponent(siteId)}/crawls/${encodeURIComponent(crawlRunId)}`,
  )

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Unable to load the crawl status.'))
  }
  return response.json() as Promise<CrawlStatusResponse>
}

export async function getSiteDetail(siteId: string): Promise<SiteDetail> {
  const response = await authenticatedFetch(
    `${apiUrl}/llms-txt/sites/${encodeURIComponent(siteId)}`,
  )

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Unable to load the website.'))
  }
  return response.json() as Promise<SiteDetail>
}

export async function getLlmsTxtVersion(
  siteId: string,
  versionId: string,
): Promise<LlmsTxtVersion> {
  const response = await authenticatedFetch(
    `${apiUrl}/llms-txt/sites/${encodeURIComponent(siteId)}/versions/${encodeURIComponent(versionId)}`,
  )

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Unable to load this llms.txt version.'))
  }
  return response.json() as Promise<LlmsTxtVersion>
}
