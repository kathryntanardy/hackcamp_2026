import brandIcon from '../assets/icons/brand-nav.svg'
import findingsIcon from '../assets/icons/findings-document.svg'
import savedIcon from '../assets/icons/nav-saved.svg'

export type TopNavbarTab = 'map' | 'findings'

export type TopNavbarProps = {
  brand?: string
  activeTab?: TopNavbarTab
  onTabChange?: (tab: TopNavbarTab) => void
  onViewSaved?: () => void
  findingsActive?: boolean
  savedActive?: boolean
}

export function TopNavbar({
  brand = 'Open Commitment Issues',
  onTabChange,
  onViewSaved,
  findingsActive = false,
  savedActive = false,
}: TopNavbarProps) {
  const mapActive = !findingsActive && !savedActive

  return (
    <header className="top-navbar" aria-label="Primary">
      <div className="top-navbar__inner">
        <nav className="top-navbar__tabs" aria-label="Views">
          <button
            type="button"
            className={`top-navbar__tab${mapActive ? ' is-active' : ''}`}
            aria-current={mapActive ? 'page' : undefined}
            onClick={() => onTabChange?.('map')}
          >
            <img src={brandIcon} alt="" width={16} height={18} />
            <span>{brand}</span>
          </button>
          <button
            type="button"
            className={`top-navbar__tab${findingsActive ? ' is-active' : ''}`}
            aria-current={findingsActive ? 'page' : undefined}
            aria-pressed={findingsActive}
            onClick={() => onTabChange?.('findings')}
          >
            <img src={findingsIcon} alt="" width={18} height={18} />
            <span>Findings</span>
          </button>
          <button
            type="button"
            className={`top-navbar__tab${savedActive ? ' is-active' : ''}`}
            aria-current={savedActive ? 'page' : undefined}
            aria-pressed={savedActive}
            onClick={() => onViewSaved?.()}
          >
            <img src={savedIcon} alt="" width={18} height={18} />
            <span>Saved</span>
          </button>
        </nav>
      </div>
    </header>
  )
}
