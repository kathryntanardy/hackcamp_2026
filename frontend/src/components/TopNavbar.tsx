import mapNavIcon from '../assets/icons/map-nav.svg'

export type TopNavbarTab = 'map' | 'findings'

export type TopNavbarProps = {
  brand?: string
  activeTab?: TopNavbarTab
  onTabChange?: (tab: TopNavbarTab) => void
}

export function TopNavbar({
  brand = 'Open Commitment Issues',
  activeTab = 'map',
  onTabChange,
}: TopNavbarProps) {
  return (
    <header className="top-navbar" aria-label="Primary">
      <div className="top-navbar__inner">
        <div className="top-navbar__left">
          <p className="top-navbar__brand">{brand}</p>
          <nav className="top-navbar__tabs" aria-label="Views">
            <button
              type="button"
              className={`top-navbar__tab${activeTab === 'map' ? ' is-active' : ''}`}
              aria-current={activeTab === 'map' ? 'page' : undefined}
              onClick={() => onTabChange?.('map')}
            >
              <img src={mapNavIcon} alt="" width={22} height={22} />
              Interactive Map
            </button>
            <button
              type="button"
              className={`top-navbar__tab${activeTab === 'findings' ? ' is-active' : ''}`}
              aria-current={activeTab === 'findings' ? 'page' : undefined}
              onClick={() => onTabChange?.('findings')}
            >
              Findings
            </button>
          </nav>
        </div>
      </div>
    </header>
  )
}
