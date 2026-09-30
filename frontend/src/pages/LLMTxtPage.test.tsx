import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LLMTxtPage } from './LLMTxtPage'

const apiMocks = vi.hoisted(() => ({
  createCrawl: vi.fn(),
  getLlmsTxtVersion: vi.fn(),
  getSiteDetail: vi.fn(),
  getCrawlStatus: vi.fn(),
}))

vi.mock('../lib/api', () => apiMocks)

describe('LLMTxtPage', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  beforeEach(() => {
    apiMocks.createCrawl.mockReset()
    apiMocks.getLlmsTxtVersion.mockReset()
    apiMocks.getSiteDetail.mockReset()
    apiMocks.getCrawlStatus.mockReset()
    apiMocks.getSiteDetail.mockResolvedValue({
      site_id: 'site-1',
      root_url: 'https://example.com/',
      created_at: '2026-09-26T12:00:00+00:00',
      updated_at: '2026-09-28T12:00:00+00:00',
      modified_at: '2026-09-28T11:00:00+00:00',
      latest_crawl: null,
      current_version: {
        site_id: 'site-1',
        version_id: 'version-2',
        crawl_run_id: 'crawl-2',
        generated_at: '2026-09-28T12:00:00+00:00',
        content_hash: 'hash-2',
        status: 'CURRENT',
        generation_method: 'KIMI_K3',
        model_id: 'us.moonshotai.kimi-k3',
        content: '# Current file',
      },
      versions: [
        {
          site_id: 'site-1',
          version_id: 'version-2',
          crawl_run_id: 'crawl-2',
          generated_at: '2026-09-28T12:00:00+00:00',
          content_hash: 'hash-2',
          status: 'CURRENT',
          generation_method: 'KIMI_K3',
          model_id: 'us.moonshotai.kimi-k3',
        },
        {
          site_id: 'site-1',
          version_id: 'version-1',
          crawl_run_id: 'crawl-1',
          generated_at: '2026-09-27T12:00:00+00:00',
          content_hash: 'hash-1',
          status: 'CURRENT',
          generation_method: 'DETERMINISTIC_FALLBACK',
          model_id: null,
        },
      ],
    })
    apiMocks.getLlmsTxtVersion.mockResolvedValue({
      site_id: 'site-1',
      version_id: 'version-1',
      crawl_run_id: 'crawl-1',
      generated_at: '2026-09-27T12:00:00+00:00',
      content_hash: 'hash-1',
      status: 'CURRENT',
      generation_method: 'DETERMINISTIC_FALLBACK',
      model_id: null,
      content: '# Previous file',
    })
    apiMocks.createCrawl.mockResolvedValue({
      site_id: 'site-1',
      crawl_run_id: 'crawl-refresh',
      url: 'https://example.com/',
      status: 'PENDING',
    })
    window.scrollTo = vi.fn()
  })

  it('shows the current file and loads a selected previous version', async () => {
    render(<LLMTxtPage onBack={vi.fn()} onSignOut={vi.fn()} siteId="site-1" />)

    expect(await screen.findByText('# Current file')).toBeTruthy()
    expect(screen.getByText('Previous versions')).toBeTruthy()

    fireEvent.click(screen.getByText('Deterministic fallback'))

    expect(await screen.findByText('# Previous file')).toBeTruthy()
    expect(apiMocks.getLlmsTxtVersion).toHaveBeenCalledWith('site-1', 'version-1')
  })

  it('starts a refresh for the current root URL and reloads site details', async () => {
    render(<LLMTxtPage onBack={vi.fn()} onSignOut={vi.fn()} siteId="site-1" />)
    expect(await screen.findByText('# Current file')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    await waitFor(() => {
      expect(apiMocks.createCrawl).toHaveBeenCalledWith('https://example.com/')
      expect(apiMocks.getSiteDetail).toHaveBeenCalledTimes(2)
    })
  })

  it('shows failure without a spinner or polling when no file exists', async () => {
    const detail = await apiMocks.getSiteDetail('site-1')
    apiMocks.getSiteDetail.mockResolvedValue({
      ...detail,
      current_version: null,
      versions: [],
      latest_crawl: {
        site_id: 'site-1', crawl_run_id: 'crawl-failed', status: 'FAILED',
        discovered_page_count: 1, completed_page_count: 0,
        failed_page_count: 1, pending_page_count: 0,
      },
    })
    const interval = vi.spyOn(window, 'setInterval')
    render(<LLMTxtPage onBack={vi.fn()} onSignOut={vi.fn()} siteId="site-1" />)

    expect(await screen.findByText('Crawl failed')).toBeTruthy()
    expect(screen.getByText('The latest crawl failed. No llms.txt file was generated.')).toBeTruthy()
    expect(screen.queryByText('The latest crawl is still processing.')).toBeNull()
    expect(screen.getByRole('status').querySelector('.spin')).toBeNull()
    expect(interval).not.toHaveBeenCalledWith(expect.any(Function), 4000)
    expect(apiMocks.getCrawlStatus).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Refresh' }).hasAttribute('disabled')).toBe(false)
  })

  it('keeps an existing file visible when the latest crawl fails', async () => {
    const detail = await apiMocks.getSiteDetail('site-1')
    apiMocks.getSiteDetail.mockResolvedValue({
      ...detail,
      latest_crawl: { site_id: 'site-1', crawl_run_id: 'crawl-failed', status: 'FAILED' },
    })
    render(<LLMTxtPage onBack={vi.fn()} onSignOut={vi.fn()} siteId="site-1" />)

    expect(await screen.findByText('# Current file')).toBeTruthy()
    expect(screen.queryByText('Crawl failed')).toBeNull()
  })

  it.each(['CRAWLING_AND_PARSING', 'GENERATING'])(
    'fetches and polls a scheduled %s run when the file page is reopened', async (status) => {
      let poll: (() => Promise<void>) | undefined
      vi.spyOn(window, 'setInterval').mockImplementation((handler) => {
        poll = handler as () => Promise<void>
        return 1
      })
      const props = { onBack: vi.fn(), onSignOut: vi.fn(), siteId: 'site-1' }
      const first = render(<LLMTxtPage {...props} />)
      await screen.findByText('# Current file')
      first.unmount()
      const detail = await apiMocks.getSiteDetail('site-1')
      const crawl = {
        site_id: 'site-1', crawl_run_id: 'scheduled-run', status,
        discovered_page_count: 12, completed_page_count: 9,
        failed_page_count: 1, pending_page_count: 2,
      }
      apiMocks.getSiteDetail.mockResolvedValue({ ...detail, latest_crawl: crawl })
      apiMocks.getCrawlStatus.mockResolvedValue(crawl)
      render(<LLMTxtPage {...props} />)
      await screen.findByText('# Current file')
      expect(screen.getByText('12')).toBeTruthy()
      expect(screen.getByText('10')).toBeTruthy()
      await act(async () => { await poll?.() })
      expect(apiMocks.getCrawlStatus).toHaveBeenCalledWith('site-1', 'scheduled-run')
    },
  )

  it('polls an active crawl and combines parsed and failed pages as completed', async () => {
    let poll: (() => Promise<void>) | null = null
    vi.spyOn(window, 'setInterval').mockImplementation((handler) => {
      poll = handler as () => Promise<void>
      return 1
    })
    apiMocks.getSiteDetail.mockResolvedValueOnce({
      site_id: 'site-1',
      root_url: 'https://example.com/',
      created_at: '2026-09-26T12:00:00+00:00',
      updated_at: '2026-09-28T12:00:00+00:00',
      modified_at: '2026-09-28T11:00:00+00:00',
      current_version: null,
      versions: [],
      latest_crawl: {
        site_id: 'site-1',
        crawl_run_id: 'crawl-active',
        status: 'CRAWLING_AND_PARSING',
        pending_page_count: 8,
        discovered_page_count: 10,
        completed_page_count: 2,
        failed_page_count: 0,
        created_at: '2026-09-28T12:00:00+00:00',
        updated_at: '2026-09-28T12:01:00+00:00',
      },
    })
    apiMocks.getCrawlStatus.mockResolvedValue({
      site_id: 'site-1',
      crawl_run_id: 'crawl-active',
      status: 'CRAWLING_AND_PARSING',
      pending_page_count: 5,
      discovered_page_count: 12,
      completed_page_count: 5,
      failed_page_count: 2,
      created_at: '2026-09-28T12:00:00+00:00',
      updated_at: '2026-09-28T12:02:00+00:00',
    })

    render(<LLMTxtPage onBack={vi.fn()} onSignOut={vi.fn()} siteId="site-1" />)
    expect(await screen.findByText('10')).toBeTruthy()

    await act(async () => {
      await poll?.()
    })

    expect(apiMocks.getCrawlStatus).toHaveBeenCalledWith('site-1', 'crawl-active')
    expect(screen.getByText('12')).toBeTruthy()
    expect(screen.getByText('7')).toBeTruthy()
  })
})
