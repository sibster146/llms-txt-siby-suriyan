import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  Check,
  Clipboard,
  Download,
  FileClock,
  FileText,
  LoaderCircle,
  LogOut,
} from 'lucide-react'
import { Brand } from '../components/Brand'
import {
  type LlmsTxtVersion,
  type LlmsTxtVersionSummary,
  type SiteDetail,
  getLlmsTxtVersion,
  getSiteDetail,
} from '../lib/api'

interface LLMTxtPageProps {
  onBack: () => void
  onSignOut: () => Promise<void>
  siteId: string
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function methodLabel(method: string | null): string {
  if (method === 'AMAZON_NOVA_PRO') return 'Amazon Nova Pro'
  if (method === 'KIMI_K3') return 'Moonshot AI Kimi K3'
  if (method === 'DETERMINISTIC_FALLBACK') return 'Deterministic fallback'
  return method?.toLowerCase().replaceAll('_', ' ') ?? 'Unknown'
}

export function LLMTxtPage({ onBack, onSignOut, siteId }: LLMTxtPageProps) {
  const [detail, setDetail] = useState<SiteDetail | null>(null)
  const [displayedVersion, setDisplayedVersion] = useState<LlmsTxtVersion | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingVersionId, setLoadingVersionId] = useState('')
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [signingOut, setSigningOut] = useState(false)

  useEffect(() => {
    let cancelled = false
    getSiteDetail(siteId)
      .then((site) => {
        if (cancelled) return
        setDetail(site)
        setDisplayedVersion(site.current_version)
      })
      .catch((requestError: unknown) => {
        if (!cancelled) {
          setError(requestError instanceof Error ? requestError.message : 'Unable to load the website.')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [siteId])

  const previousVersions = useMemo(() => {
    const currentId = detail?.current_version?.version_id
    return detail?.versions.filter((version) => version.version_id !== currentId) ?? []
  }, [detail])

  async function selectVersion(version: LlmsTxtVersionSummary) {
    if (version.version_id === displayedVersion?.version_id) return
    setLoadingVersionId(version.version_id)
    setError('')
    try {
      setDisplayedVersion(await getLlmsTxtVersion(siteId, version.version_id))
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load this version.')
    } finally {
      setLoadingVersionId('')
    }
  }

  async function copyContent() {
    if (!displayedVersion) return
    await navigator.clipboard.writeText(displayedVersion.content)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }

  function downloadContent() {
    if (!displayedVersion) return
    const url = URL.createObjectURL(new Blob([displayedVersion.content], { type: 'text/plain' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'llms.txt'
    link.click()
    URL.revokeObjectURL(url)
  }

  async function handleSignOut() {
    setSigningOut(true)
    try {
      await onSignOut()
    } finally {
      setSigningOut(false)
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

      <section className="detail-workspace">
        <button className="detail-back" onClick={onBack} type="button">
          <ArrowLeft size={16} />
          All websites
        </button>

        {loading ? (
          <div className="workspace-empty" aria-label="Loading llms.txt">
            <LoaderCircle className="spin" size={24} />
          </div>
        ) : error && !detail ? (
          <p className="error" role="alert">{error}</p>
        ) : detail ? (
          <>
            <div className="detail-heading">
              <div>
                <p className="eyebrow">Website llms.txt</p>
                <h1>{new URL(detail.root_url).hostname}</h1>
                <a href={detail.root_url} rel="noreferrer" target="_blank">{detail.root_url}</a>
              </div>
              {detail.current_version && displayedVersion?.version_id !== detail.current_version.version_id && (
                <button className="secondary-button" onClick={() => setDisplayedVersion(detail.current_version)} type="button">
                  View current
                </button>
              )}
            </div>

            {error && <p className="error" role="alert">{error}</p>}

            {displayedVersion ? (
              <section className="llms-file" aria-labelledby="llms-file-title">
                <div className="llms-file-toolbar">
                  <div>
                    <div className="file-title-row">
                      <FileText size={18} />
                      <h2 id="llms-file-title">llms.txt</h2>
                      {displayedVersion.version_id === detail.current_version?.version_id && <span className="current-label">Current</span>}
                    </div>
                    <p>Generated {formatDate(displayedVersion.generated_at)}</p>
                  </div>
                  <div className="file-actions">
                    <button aria-label="Copy llms.txt" className="icon-button" onClick={copyContent} title="Copy llms.txt" type="button">
                      {copied ? <Check size={18} /> : <Clipboard size={18} />}
                    </button>
                    <button aria-label="Download llms.txt" className="icon-button" onClick={downloadContent} title="Download llms.txt" type="button">
                      <Download size={18} />
                    </button>
                  </div>
                </div>
                <dl className="file-metadata">
                  <div><dt>Version</dt><dd>{displayedVersion.version_id}</dd></div>
                  <div><dt>Created by</dt><dd>{methodLabel(displayedVersion.generation_method)}</dd></div>
                  <div><dt>Content hash</dt><dd>{displayedVersion.content_hash}</dd></div>
                </dl>
                <pre className="llms-content">{displayedVersion.content}</pre>
              </section>
            ) : (
              <div className="generation-empty">
                <LoaderCircle className="spin" size={22} />
                <div>
                  <strong>No generated file yet</strong>
                  <p>The latest crawl is still processing.</p>
                </div>
              </div>
            )}

            <section className="version-history" aria-labelledby="version-history-title">
              <div className="section-heading">
                <div>
                  <h2 id="version-history-title">Previous versions</h2>
                  <p>Earlier files generated for this website.</p>
                </div>
                <span>{previousVersions.length}</span>
              </div>
              {previousVersions.length === 0 ? (
                <div className="history-empty">No previous versions</div>
              ) : (
                <div className="version-list">
                  {previousVersions.map((version) => (
                    <button
                      className={`version-row${displayedVersion?.version_id === version.version_id ? ' selected' : ''}`}
                      disabled={loadingVersionId === version.version_id}
                      key={version.version_id}
                      onClick={() => selectVersion(version)}
                      type="button"
                    >
                      <FileClock size={18} />
                      <span className="version-row-main">
                        <strong>{formatDate(version.generated_at)}</strong>
                        <small>{version.version_id}</small>
                      </span>
                      <span className="version-method">{methodLabel(version.generation_method)}</span>
                      {loadingVersionId === version.version_id && <LoaderCircle className="spin" size={17} />}
                    </button>
                  ))}
                </div>
              )}
            </section>
          </>
        ) : null}
      </section>
    </main>
  )
}
