import { type FormEvent, useEffect, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  FileText,
  Globe2,
  LoaderCircle,
  LogOut,
  Plus,
  X,
} from 'lucide-react'
import { Brand } from '../components/Brand'
import {
  type CrawlStatus,
  type CrawlStatusResponse,
  type SiteSummary,
  createCrawl,
  getCrawlStatus,
  listSites,
} from '../lib/api'
import type { AuthenticatedUser } from '../lib/auth'

interface HomePageProps {
  onSignOut: () => Promise<void>
  onSelectSite: (siteId: string) => void
  user: AuthenticatedUser
}

const terminalStatuses: CrawlStatus[] = ['COMPLETED', 'FAILED']

function statusLabel(status: CrawlStatus): string {
  const label = status.toLowerCase().replaceAll('_', ' ')
  return label.charAt(0).toUpperCase() + label.slice(1)
}

export function HomePage({ onSelectSite, onSignOut, user }: HomePageProps) {
  const [signingOut, setSigningOut] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')
  const [pollError, setPollError] = useState('')
  const [sitesError, setSitesError] = useState('')
  const [loadingSites, setLoadingSites] = useState(true)
  const [sites, setSites] = useState<SiteSummary[]>([])

  useEffect(() => {
    let cancelled = false

    async function loadSites() {
      try {
        const loadedSites = await listSites()
        if (!cancelled) setSites(loadedSites)
      } catch (error) {
        if (!cancelled) {
          setSitesError(error instanceof Error ? error.message : 'Unable to load your websites.')
        }
      } finally {
        if (!cancelled) setLoadingSites(false)
      }
    }

    void loadSites()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!modalOpen) return

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape' && !creating) setModalOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [creating, modalOpen])

  useEffect(() => {
    const activeCrawls = sites.flatMap((site) => {
      const crawl = site.latest_crawl
      return crawl && !terminalStatuses.includes(crawl.status)
        ? [{ siteId: site.site_id, crawlRunId: crawl.crawl_run_id }]
        : []
    })
    if (activeCrawls.length === 0) return

    let cancelled = false
    let polling = false
    const timer = window.setInterval(async () => {
      if (polling) return
      polling = true
      const results = await Promise.allSettled(
        activeCrawls.map(({ siteId, crawlRunId }) => getCrawlStatus(siteId, crawlRunId)),
      )
      polling = false
      if (cancelled) return

      const refreshed = new Map<string, CrawlStatusResponse>()
      let firstError = ''
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          refreshed.set(activeCrawls[index].siteId, result.value)
        } else if (!firstError) {
          firstError = result.reason instanceof Error
            ? result.reason.message
            : 'Unable to refresh the crawl status.'
        }
      })
      if (refreshed.size > 0) {
        setSites((current) => current.map((site) => ({
          ...site,
          latest_crawl: refreshed.get(site.site_id) ?? site.latest_crawl,
        })))
      }
      setPollError(firstError)
    }, 4000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [sites])

  async function handleSignOut() {
    setSigningOut(true)
    try {
      await onSignOut()
    } finally {
      setSigningOut(false)
    }
  }

  function openModal() {
    setUrl('')
    setCreateError('')
    setModalOpen(true)
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setCreateError('')
    setCreating(true)
    try {
      await createCrawl(url.trim())
      try {
        setSites(await listSites())
        setSitesError('')
      } catch (error) {
        setSitesError(error instanceof Error ? error.message : 'Unable to refresh your websites.')
      }
      setPollError('')
      setModalOpen(false)
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : 'Unable to create the crawl.')
    } finally {
      setCreating(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <Brand />
        <button className="icon-text-button" disabled={signingOut} onClick={handleSignOut} type="button">
          {signingOut ? <LoaderCircle className="spin" size={17} /> : <LogOut size={17} />}
          Sign out
        </button>
      </header>
      <section className="workspace">
        <div className="workspace-heading">
          <div>
            <p className="eyebrow">Signed in as {user.email}</p>
            <h1>Your websites</h1>
          </div>
          <button className="primary-action" onClick={openModal} type="button">
            <Plus size={18} />
            New website
          </button>
        </div>

        {loadingSites ? (
          <div className="workspace-empty" aria-label="Loading websites">
            <LoaderCircle className="spin" size={24} />
          </div>
        ) : sites.length === 0 ? (
          <div className="workspace-empty">
            <FileText size={24} />
            <strong>No websites yet</strong>
          </div>
        ) : (
          <div className="crawl-list" aria-live="polite">
            {sites.map((site) => {
              const crawl = site.latest_crawl
              const crawlStatus = crawl?.status
              return (
                <div className="site-entry" key={site.site_id}>
                  <a
                    className="site-entry-link"
                    href={`/sites/${encodeURIComponent(site.site_id)}`}
                    onClick={(event) => {
                      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
                      event.preventDefault()
                      onSelectSite(site.site_id)
                    }}
                  >
                    <article className="crawl-item">
                      <div className="crawl-icon"><Globe2 size={20} /></div>
                      <div className="crawl-primary">
                        <strong>{site.root_url}</strong>
                        <span>{crawl?.crawl_run_id ?? site.last_crawl_run_id}</span>
                      </div>
                      {crawlStatus && (
                        <div className={`status-badge status-${crawlStatus.toLowerCase()}`}>
                          {crawlStatus === 'COMPLETED' ? <CheckCircle2 size={15} /> : crawlStatus === 'FAILED' ? <AlertCircle size={15} /> : crawlStatus === 'WORKING' || crawlStatus === 'CRAWLED' || crawlStatus === 'GENERATION_QUEUED' || crawlStatus === 'GENERATING' ? <LoaderCircle className="spin" size={15} /> : <Clock3 size={15} />}
                          {statusLabel(crawlStatus)}
                        </div>
                      )}
                    </article>
                    {crawl && (
                      <div className="crawl-counts">
                        <span>{crawl.discovered_page_count} discovered</span>
                        <span>{crawl.completed_page_count} completed</span>
                        <span>{crawl.failed_page_count} failed</span>
                      </div>
                    )}
                  </a>
                </div>
              )
            })}
            {sitesError && <p className="inline-error" role="alert">{sitesError}</p>}
            {pollError && <p className="inline-error" role="alert">{pollError}</p>}
          </div>
        )}
        {sitesError && sites.length === 0 && !loadingSites && (
          <p className="error workspace-error" role="alert">{sitesError}</p>
        )}
      </section>

      {modalOpen && (
        <div className="modal-backdrop" onMouseDown={() => !creating && setModalOpen(false)}>
          <section aria-labelledby="create-dialog-title" aria-modal="true" className="modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
            <div className="modal-header">
              <div>
                <p className="eyebrow">New website</p>
                <h2 id="create-dialog-title">Create llms.txt</h2>
              </div>
              <button aria-label="Close" className="icon-button" disabled={creating} onClick={() => setModalOpen(false)} title="Close" type="button">
                <X size={19} />
              </button>
            </div>
            <form className="create-form" onSubmit={handleCreate}>
              <label htmlFor="website-url">Website URL</label>
              <div className="input-wrap">
                <Globe2 aria-hidden="true" size={18} />
                <input autoFocus id="website-url" onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com" required type="url" value={url} />
              </div>
              {createError && <p className="error" role="alert">{createError}</p>}
              <div className="modal-actions">
                <button className="secondary-button" disabled={creating} onClick={() => setModalOpen(false)} type="button">Cancel</button>
                <button className="create-button" disabled={creating} type="submit">
                  {creating && <LoaderCircle className="spin" size={17} />}
                  Create
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </main>
  )
}
