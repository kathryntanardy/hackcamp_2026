import layoutIcon from '../assets/flower-map/layout.svg'
import mapNavIcon from '../assets/flower-map/map.svg'

export type TopNavbarTab = 'map' | 'findings'

export type TopNavbarProps = {
  brand?: string
  activeTab?: TopNavbarTab
  onTabChange?: (tab: TopNavbarTab) => void
  findingsActive?: boolean
  sidebarOpen?: boolean
  onToggleSidebar?: () => void
  savedActive?: boolean
}

export function TopNavbar({
  brand = 'Open Commitment Issues',
  onTabChange,
  sidebarOpen = false,
  onToggleSidebar,
  findingsActive = false,
  savedActive = false,
}: TopNavbarProps) {
  return (
    <header className="top-navbar" aria-label="Primary">
      <div className="top-navbar__inner">
        <div className="top-navbar__left">
          <button
            type="button"
            className="top-navbar__brand"
            aria-current={!findingsActive && !savedActive ? 'page' : undefined}
            onClick={() => onTabChange?.('map')}
          >
            {brand}
          </button>
          <nav className="top-navbar__tabs" aria-label="Views">
            <button type="button"
              className={`top-navbar__tab${!findingsActive && !savedActive ? ' is-active' : ''}`}
              aria-current={!findingsActive && !savedActive ? 'page' : undefined}
              onClick={() => onTabChange?.('map')}>
              <img src={mapNavIcon} alt="" width={22} height={22} />
              <span>Interactive Map</span>
            </button>
            <button
              type="button"
              className={`top-navbar__tab${findingsActive ? ' is-active' : ''}`}
              aria-current={findingsActive ? 'page' : undefined}
              aria-pressed={findingsActive}
              onClick={() => onTabChange?.('findings')}
            >
              Findings
            </button>
          </nav>
        </div>
        <button type="button" className="top-navbar__layout" aria-label="Toggle repository panel"
          aria-expanded={sidebarOpen} onClick={onToggleSidebar}>
          <img src={layoutIcon} width={24} height={24} alt="" />
        </button>
      </div>
    </header>
  )
}
