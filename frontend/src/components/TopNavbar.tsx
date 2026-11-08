import mapNavIcon from '../assets/icons/map-nav.svg'

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
  return (
    <header className="top-navbar" aria-label="Primary">
      <div className="top-navbar__inner">
        <div className="top-navbar__left">
          <button
            type="button"
            className="top-navbar__brand is-active"
            aria-current={!findingsActive && !savedActive ? 'page' : undefined}
            onClick={() => onTabChange?.('map')}
          >
            <img src={mapNavIcon} alt="" width={22} height={22} />
            {brand}
          </button>
          <nav className="top-navbar__tabs" aria-label="Views">
            <button
              type="button"
              className={`top-navbar__tab${findingsActive ? ' is-active' : ''}`}
              aria-current={findingsActive ? 'page' : undefined}
              aria-pressed={findingsActive}
              onClick={() => onTabChange?.('findings')}
            >
              Findings
            </button>
            {onViewSaved ? (
              <button
                type="button"
                className={`top-navbar__tab${savedActive ? ' is-active' : ''}`}
                aria-current={savedActive ? 'page' : undefined}
                aria-pressed={savedActive}
                onClick={onViewSaved}
              >
                Saved
              </button>
            ) : null}
          </nav>
        </div>
      </div>
    </header>
  )
}
