import reposMetaIcon from '../assets/icons/repos-meta.svg'
import cornerDownRightIcon from '../assets/icons/corner-down-right.svg'

export type RepoListItem = {
  id: string
  name: string
  description: string
  vulnerabilityLabel: string
  vulnerabilityTone: 'high' | 'medium' | 'low' | 'none'
  vulnerabilityScore: string
  category: string
}

export type RepoListSidebarProps = {
  title?: string
  metaLabel?: string
  countLabel?: string
  scoreLabel?: string
  categoryLabel?: string
  emptyLabel?: string
  repos?: RepoListItem[]
  loading?: boolean
  error?: string | null
  selectedId?: string | null
  onSelectRepo?: (id: string) => void
}

function toneClass(tone: RepoListItem['vulnerabilityTone']): string {
  if (tone === 'high') return 'is-high'
  if (tone === 'medium') return 'is-medium'
  if (tone === 'low') return 'is-low'
  return 'is-none'
}

export function RepoListSidebar({
  title = 'Open-Source Repositories',
  metaLabel = 'Open-source repositories',
  countLabel,
  scoreLabel = 'Maintenance:',
  categoryLabel = 'Category:',
  emptyLabel = 'No overview available.',
  repos = [],
  loading = false,
  error = null,
  selectedId = null,
  onSelectRepo,
}: RepoListSidebarProps) {
  const resolvedCount =
    countLabel ??
    `${repos.length} ${repos.length === 1 ? 'repository' : 'repositories'}`

  return (
    <aside className="repo-list-sidebar" aria-label={title}>
      <header className="repo-list-sidebar__top">
        <div className="repo-list-sidebar__meta">
          <img src={reposMetaIcon} alt="" width={17} height={17} />
          <span>{metaLabel}</span>
        </div>
      </header>

      <div className="repo-list-sidebar__hero">
        <h1 className="repo-list-sidebar__title">{title}</h1>
      </div>

      <div className="repo-list-sidebar__body">
        {loading ? (
          <p className="repo-list-sidebar__status">Loading repositories…</p>
        ) : error ? (
          <p className="repo-list-sidebar__status is-error" role="alert">
            {error}
          </p>
        ) : (
          <>
            <p className="repo-list-sidebar__count">{resolvedCount}</p>
            <ul className="repo-list">
              {repos.map((repo) => (
                <li key={repo.id}>
                  <button
                    type="button"
                    className={`repo-card${selectedId === repo.id ? ' is-selected' : ''}`}
                    aria-current={selectedId === repo.id ? 'true' : undefined}
                    onClick={() => onSelectRepo?.(repo.id)}
                  >
                    <div className="repo-card__main">
                      {repo.vulnerabilityTone !== 'none' ? (
                        <span className={`vuln-badge ${toneClass(repo.vulnerabilityTone)}`}>
                          <span className="vuln-badge__swatch" aria-hidden="true" />
                          {repo.vulnerabilityLabel}
                        </span>
                      ) : null}
                      <div className="repo-card__copy">
                        <p className="repo-card__name">{repo.name}</p>
                        <div className="repo-card__desc-row">
                          <img src={cornerDownRightIcon} alt="" width={16} height={16} />
                          <p className="repo-card__desc">
                            {repo.description || emptyLabel}
                          </p>
                        </div>
                      </div>
                    </div>
                    <div className="repo-card__footer">
                      <p className="repo-card__metric">
                        <span className="repo-card__metric-label">{scoreLabel}</span>{' '}
                        <span
                          className={`repo-card__metric-value${
                            repo.vulnerabilityTone === 'high' ? ' is-danger' : ''
                          }`}
                        >
                          {repo.vulnerabilityScore}
                        </span>
                      </p>
                      <p className="repo-card__metric">
                        <span className="repo-card__metric-label">{categoryLabel}</span>{' '}
                        <span className="repo-card__metric-value">{repo.category}</span>
                      </p>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </aside>
  )
}
