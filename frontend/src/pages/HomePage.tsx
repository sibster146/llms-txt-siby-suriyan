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
  type CreateCrawlResponse,
  type SiteSummary,
  createCrawl,
  getCrawlStatus,
  listSites,
} from '../lib/api'
import type { AuthenticatedUser } from '../lib/auth'

interface HomePageProps {
  onSignOut: () => Promise<void>
  user: AuthenticatedUser
}

interface ActiveCrawl extends Omit<CreateCrawlResponse, 'status'> {
  status: CrawlStatus
  details?: CrawlStatusResponse
}

const terminalStatuses: CrawlStatus[] = ['CRAWLED', 'COMPLETED', 'FAILED']

function statusLabel(status: CrawlStatus): string {
  return status.charAt(0) + status.slice(1).toLowerCase()
}

export function HomePage({ onSignOut, user }: HomePageProps) {
  const [signingOut, setSigningOut] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')
  const [pollError, setPollError] = useState('')
  const [sitesError, setSitesError] = useState('')
  const [loadingSites, setLoadingSites] = useState(true)
  const [sites, setSites] = useState<SiteSummary[]>([])
  const [activeCrawl, setActiveCrawl] = useState<ActiveCrawl | null>(null)
  const activeSiteId = activeCrawl?.site_id
  const activeCrawlRunId = activeCrawl?.crawl_run_id
  const crawlStatus = activeCrawl?.status

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
    if (!activeSiteId || !activeCrawlRunId || !crawlStatus || terminalStatuses.includes(crawlStatus)) return
    const siteId = activeSiteId
    const crawlRunId = activeCrawlRunId

    let cancelled = false
    let timer: number

    async function poll() {
      try {
        const latest = await getCrawlStatus(
          siteId,
          crawlRunId,
        )
        if (cancelled) return
        setActiveCrawl((current) => current ? { ...current, status: latest.status, details: latest } : null)
        setPollError('')
        if (!terminalStatuses.includes(latest.status)) {
          timer = window.setTimeout(poll, 4000)
        }
      } catch (error) {
        if (cancelled) return
        setPollError(error instanceof Error ? error.message : 'Unable to refresh the crawl status.')
        timer = window.setTimeout(poll, 4000)
      }
    }

    timer = window.setTimeout(poll, 4000)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [activeCrawlRunId, activeSiteId, crawlStatus])

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
      const crawl = await createCrawl(url.trim())
      setActiveCrawl(crawl)
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
              const isActive = activeCrawl?.site_id === site.site_id
                && activeCrawl.crawl_run_id === site.last_crawl_run_id
              return (
                <div className="site-entry" key={site.site_id}>
                  <article className="crawl-item">
                    <div className="crawl-icon"><Globe2 size={20} /></div>
                    <div className="crawl-primary">
                      <strong>{site.root_url}</strong>
                      <span>{site.last_crawl_run_id}</span>
                    </div>
                    {isActive && crawlStatus && (
                      <div className={`status-badge status-${crawlStatus.toLowerCase()}`}>
                        {crawlStatus === 'CRAWLED' || crawlStatus === 'COMPLETED' ? <CheckCircle2 size={15} /> : crawlStatus === 'FAILED' ? <AlertCircle size={15} /> : crawlStatus === 'WORKING' ? <LoaderCircle className="spin" size={15} /> : <Clock3 size={15} />}
                        {statusLabel(crawlStatus)}
                      </div>
                    )}
                  </article>
                  {isActive && activeCrawl.details && (
                    <div className="crawl-counts">
                      <span>{activeCrawl.details.discovered_page_count} discovered</span>
                      <span>{activeCrawl.details.completed_page_count} completed</span>
                      <span>{activeCrawl.details.failed_page_count} failed</span>
                    </div>
                  )}
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
