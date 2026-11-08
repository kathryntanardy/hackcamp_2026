import { FLOWER_PALETTE, type FlowerCluster, type VulnSeverity } from '../map/flowers'

export type FlowerLabelProps = {
  flower: FlowerCluster
  x: number
  y: number
  activeTone?: VulnSeverity | null
  /** True when this whole category (not a High/Med/Low band) is the list filter. */
  categoryActive?: boolean
  onHoverTone?: (tone: VulnSeverity | null) => void
  onSelectTone?: (tone: VulnSeverity) => void
  onFocusFlower?: () => void
}

const TONES: { tone: VulnSeverity; short: string; countKey: 'high' | 'medium' | 'low' }[] = [
  { tone: 'high', short: 'High', countKey: 'high' },
  { tone: 'medium', short: 'Med', countKey: 'medium' },
  { tone: 'low', short: 'Low', countKey: 'low' },
]

export function FlowerLabel({
  flower,
  x,
  y,
  activeTone = null,
  categoryActive = false,
  onHoverTone,
  onSelectTone,
  onFocusFlower,
}: FlowerLabelProps) {
  const palette = FLOWER_PALETTE[flower.colorIndex % FLOWER_PALETTE.length]
  const title = flower.label === 'No GitHub advisories' ? 'No advisories' : flower.label

  return (
    <div
      className="flower-label"
      style={{ left: x, top: y }}
      onPointerLeave={() => onHoverTone?.(null)}
    >
      <button
        type="button"
        className={`flower-label__title${categoryActive ? ' is-active' : ''}`}
        style={{ background: palette.chipBg, color: palette.glyph }}
        aria-label={`Show ${title} repositories`}
        aria-pressed={categoryActive}
        onClick={() => onFocusFlower?.()}
      >
        <span
          className="flower-label__swatch"
          style={{ background: palette.glyph }}
          aria-hidden="true"
        />
        <span className="flower-label__name">{title}</span>
      </button>
      <div className="flower-label__counts" role="group" aria-label={`${title} severity counts`}>
        {TONES.map(({ tone, short, countKey }, index) => {
          const count = flower.counts[countKey]
          const active = activeTone === tone
          return (
            <span key={tone} className="flower-label__count-wrap">
              {index > 0 ? <span className="flower-label__divider" aria-hidden="true" /> : null}
              <button
                type="button"
                className={`flower-label__count${active ? ' is-active' : ''}`}
                aria-pressed={active}
                onPointerEnter={() => onHoverTone?.(tone)}
                onFocus={() => onHoverTone?.(tone)}
                onClick={() => onSelectTone?.(tone)}
              >
                <span className="flower-label__count-num">{count}</span>
                {` ${short}`}
              </button>
            </span>
          )
        })}
      </div>
    </div>
  )
}
