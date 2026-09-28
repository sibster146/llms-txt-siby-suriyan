import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LLMTxtPage } from './LLMTxtPage'

const apiMocks = vi.hoisted(() => ({
  getLlmsTxtVersion: vi.fn(),
  getSiteDetail: vi.fn(),
}))

vi.mock('../lib/api', () => apiMocks)

describe('LLMTxtPage', () => {
  beforeEach(() => {
    apiMocks.getLlmsTxtVersion.mockReset()
    apiMocks.getSiteDetail.mockReset()
    apiMocks.getSiteDetail.mockResolvedValue({
      site_id: 'site-1',
      root_url: 'https://example.com/',
      created_at: '2026-09-26T12:00:00+00:00',
      updated_at: '2026-09-28T12:00:00+00:00',
      modified_at: '2026-09-28T11:00:00+00:00',
      current_version: {
        site_id: 'site-1',
        version_id: 'version-2',
        crawl_run_id: 'crawl-2',
        generated_at: '2026-09-28T12:00:00+00:00',
        content_hash: 'hash-2',
        status: 'CURRENT',
        generation_method: 'AMAZON_NOVA_PRO',
        model_id: 'amazon.nova-pro-v1:0',
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
          generation_method: 'AMAZON_NOVA_PRO',
          model_id: 'amazon.nova-pro-v1:0',
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
    window.scrollTo = vi.fn()
  })

  it('shows the current file and loads a selected previous version', async () => {
    render(<LLMTxtPage onBack={vi.fn()} onSignOut={vi.fn()} siteId="site-1" />)

    expect(await screen.findByText('# Current file')).toBeTruthy()
    expect(screen.getByText('Previous versions')).toBeTruthy()

    fireEvent.click(screen.getByText('version-1'))

    expect(await screen.findByText('# Previous file')).toBeTruthy()
    expect(apiMocks.getLlmsTxtVersion).toHaveBeenCalledWith('site-1', 'version-1')
  })
})
