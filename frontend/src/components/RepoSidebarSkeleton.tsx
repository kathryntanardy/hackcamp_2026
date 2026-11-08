import { useEffect, useState, type MouseEvent } from 'react'
import languageIcon from '../assets/icons/language.svg'
import starIcon from '../assets/icons/star.svg'
import savedBookmarkIcon from '../assets/icons/saved-bookmark.svg'
import arrowExtIcon from '../assets/icons/arrow-ext.svg'

export type RepoSidebarSkeletonProps = {
  repoId: string
  language?: string | null
  onBack?: () => void
  backLabel?: string
}

const COLS = 47

/** Build a dotted row with an optional centered motif. */
function bloomRow(motif = ''): string {
  const cells = Array.from({ length: COLS }, () => '·')
  if (motif) {
    const start = Math.floor((COLS - motif.length) / 2)
    for (let i = 0; i < motif.length; i += 1) {
      cells[start + i] = motif[i] === ' ' ? '·' : motif[i]!
    }
  }
  return cells.join(' ')
}

/** Three-row bloom: top / middle / bottom motifs grow together. */
function bloomFrame(top: string, mid: string, bottom: string): string {
  return [bloomRow(top), bloomRow(mid), bloomRow(bottom)].join('\n')
}

const BLOOM_FRAMES = [
  bloomFrame('', '', ''),
  bloomFrame('', '✦', ''),
  bloomFrame('✦', '✦✿✦', '✦'),
  bloomFrame('✦✿✦', '✦✿·✿✦', '✦✿✦'),
  bloomFrame('✦✿·✿✦', '✦✿·✦·✿✦', '✦✿·✿✦'),
  bloomFrame('✦✿✦', '✦✿·✿✦', '✦✿✦'),
  bloomFrame('✦', '✦✿✦', '✦'),
  bloomFrame('', '✦', ''),
] as const

const BLOOM_FRAME_MS = 140

function splitRepoId(repoId: string): { owner: string; name: string } {
  const slash = repoId.indexOf('/')
  if (slash <= 0 || slash === repoId.length - 1) {
    return { owner: '—', name: repoId }
  }
  return {
    owner: repoId.slice(0, slash),
    name: repoId.slice(slash + 1),
  }
}

function blockFlowerInteract(event: MouseEvent) {
  event.preventDefault()
}

export function AsciiBloomDescription({ label = 'Loading repository' }: { label?: string }) {
  const [frame, setFrame] = useState(0)
  const [animate, setAnimate] = useState(true)

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => setAnimate(!media.matches)
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])

  useEffect(() => {
    if (!animate) return
    const id = window.setInterval(() => {
      setFrame((n) => (n + 1) % BLOOM_FRAMES.length)
    }, BLOOM_FRAME_MS)
    return () => window.clearInterval(id)
  }, [animate])

  const art = BLOOM_FRAMES[animate ? frame : 4]

  return (
    <div
      className="ascii-loader ascii-loader--description"
      role="status"
      onContextMenu={blockFlowerInteract}
      onDragStart={blockFlowerInteract}
    >
      <span className="visually-hidden">{label}</span>
      <pre
        className="ascii-loader__art"
        aria-hidden="true"
        draggable={false}
        onContextMenu={blockFlowerInteract}
        onDragStart={blockFlowerInteract}
      >
        {art}
      </pre>
    </div>
  )
}

export function RepoSidebarSkeleton({
  repoId,
  language = null,
  onBack,
  backLabel = '← Repositories',
}: RepoSidebarSkeletonProps) {
  const { owner, name } = splitRepoId(repoId)
  const githubUrl = `https://github.com/${repoId}`

  return (
    <aside
      className="repo-sidebar repo-sidebar--loading"
      aria-label="Repository details"
      aria-busy="true"
    >
      <header className="repo-sidebar__top">
        <div className="repo-sidebar__meta">
          {onBack ? (
            <button type="button" className="repo-sidebar__back" onClick={onBack}>
              {backLabel}
            </button>
          ) : null}
          <span className="repo-sidebar__meta-item">
            <img src={languageIcon} alt="" width={17} height={17} draggable={false} />
            {language || (
              <span className="skeleton-bar skeleton-bar--meta" aria-hidden="true" />
            )}
          </span>
          <span aria-hidden="true">|</span>
          <span className="repo-sidebar__meta-item">
            <img src={starIcon} alt="" width={17} height={17} draggable={false} />
            <span className="skeleton-bar skeleton-bar--meta" aria-hidden="true" />
          </span>
        </div>
      </header>

      <div className="repo-sidebar__title-block">
        <div className="repo-sidebar__title-row">
          <span className="repo-sidebar__star-btn" aria-hidden="true">
            <img src={savedBookmarkIcon} alt="" width={18} height={18} draggable={false} />
          </span>
          <div className="repo-sidebar__title-main">
            <div className="repo-sidebar__name-row">
              <div className="repo-sidebar__name-wrap">
                <h1 className="repo-sidebar__name">{name}</h1>
                <a
                  className="repo-sidebar__ext-link"
                  href={githubUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label="Open on GitHub"
                >
                  <img src={arrowExtIcon} alt="" width={24} height={24} draggable={false} />
                </a>
              </div>
            </div>
            <div className="repo-sidebar__owner-row">
              <p className="repo-sidebar__owner">{owner}</p>
              <p className="repo-sidebar__repo-id">{repoId}</p>
            </div>
            <div className="chip-row" aria-hidden="true">
              <span className="skeleton-bar skeleton-bar--chip" />
              <span className="skeleton-bar skeleton-bar--chip skeleton-bar--chip-wide" />
            </div>
          </div>
        </div>
      </div>

      <nav className="repo-sidebar__tabs" aria-label="Repository sections">
        <span className="repo-sidebar__tab is-active" aria-current="page">
          Overview
        </span>
        <span className="repo-sidebar__tab">Agent Process</span>
        <span className="repo-sidebar__tab">Security Scan</span>
      </nav>

      <div className="repo-sidebar__body">
        <AsciiBloomDescription />

        <section className="section" aria-hidden="true">
          <h2 className="section-heading">Key Signals</h2>
          <div className="signal-grid">
            {Array.from({ length: 4 }, (_, i) => (
              <article className="signal-card skeleton-card" key={i}>
                <span className="skeleton-bar skeleton-bar--label" />
                <span className="skeleton-bar skeleton-bar--value" />
                <span className="skeleton-bar skeleton-bar--line-short" />
              </article>
            ))}
          </div>
        </section>

        <section className="section" aria-hidden="true">
          <h2 className="section-heading">Maintenance</h2>
          <div className="health-row skeleton-health">
            <div className="health-score">
              <span className="skeleton-bar skeleton-bar--value" />
              <span className="skeleton-bar skeleton-bar--label" />
            </div>
            <div className="health-metrics">
              {Array.from({ length: 3 }, (_, i) => (
                <div className="health-metric" key={i}>
                  <span className="skeleton-bar skeleton-bar--meta" />
                  <span className="skeleton-bar skeleton-bar--meta" />
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </aside>
  )
}
