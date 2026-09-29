import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HomePage } from './HomePage'

const apiMocks = vi.hoisted(() => ({
  listSites: vi.fn(),
}))

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>()
  return {
    ...actual,
    createCrawl: vi.fn(),
    getCrawlStatus: vi.fn(),
    listSites: apiMocks.listSites,
  }
})

describe('HomePage', () => {
  beforeEach(() => {
    apiMocks.listSites.mockResolvedValue([
      {
        site_id: 'site-1',
        root_url: 'https://example.com/',
        last_crawl_run_id: 'crawl-1',
        created_at: '2026-09-28T00:00:00Z',
        updated_at: '2026-09-28T00:00:00Z',
        modified_at: null,
        latest_crawl: {
          site_id: 'site-1',
          crawl_run_id: 'crawl-1',
          status: 'COMPLETED',
          pending_page_count: 0,
          discovered_page_count: 12,
          completed_page_count: 9,
          failed_page_count: 3,
          created_at: '2026-09-28T00:00:00Z',
          updated_at: '2026-09-28T00:05:00Z',
        },
      },
    ])
  })

  it('places the create tile first and combines successful and failed page counts', async () => {
    const { container } = render(
      <HomePage
        onSelectSite={vi.fn()}
        onSignOut={vi.fn()}
        user={{ email: 'user@example.com', id: 'user-1' }}
      />,
    )

    await waitFor(() => expect(screen.getByText('https://example.com/')).toBeTruthy())

    const tiles = container.querySelectorAll('.site-grid > .site-tile')
    expect(tiles).toHaveLength(2)
    expect(tiles[0].textContent).toContain('New website')
    expect(tiles[1].textContent).toContain('12 Discovered')
    expect(tiles[1].textContent).toContain('12 Completed')
    expect(tiles[1].textContent).not.toContain('Failed')
  })
})
