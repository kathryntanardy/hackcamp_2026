import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react'

const DEFAULT_WIDTH = 580
const MIN_WIDTH = 320
const MAX_WIDTH = 800

export type SidebarPanelProps = {
  children: ReactNode
  open?: boolean
  width?: number
  onWidthChange?: (width: number) => void
}

function clampWidth(width: number, viewport = window.innerWidth): number {
  const max = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.floor(viewport * 0.46)))
  return Math.min(max, Math.max(MIN_WIDTH, Math.round(width)))
}

export function SidebarPanel({
  children,
  open = true,
  width: controlledWidth,
  onWidthChange,
}: SidebarPanelProps) {
  const [uncontrolledWidth, setUncontrolledWidth] = useState(DEFAULT_WIDTH)
  const width = controlledWidth ?? uncontrolledWidth
  const [dragging, setDragging] = useState(false)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(width)

  const setWidth = useCallback(
    (next: number) => {
      const clamped = clampWidth(next)
      if (onWidthChange) onWidthChange(clamped)
      else setUncontrolledWidth(clamped)
    },
    [onWidthChange],
  )

  useEffect(() => {
    const onResize = () => setWidth(width)
    onResize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [setWidth, width])

  function finishDrag(target: HTMLDivElement, pointerId: number) {
    setDragging(false)
    if (target.hasPointerCapture(pointerId)) {
      target.releasePointerCapture(pointerId)
    }
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (!open) return
    event.preventDefault()
    dragStartX.current = event.clientX
    dragStartWidth.current = width
    setDragging(true)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (!dragging) return
    const raw = dragStartWidth.current + (dragStartX.current - event.clientX)
    setWidth(raw)
  }

  function endDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (!dragging) return
    finishDrag(event.currentTarget, event.pointerId)
  }

  return (
    <aside
      className={[
        'sidebar-panel',
        open ? 'is-open' : 'is-closed',
        dragging ? 'is-dragging' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      style={{
        ['--sidebar-panel-width' as string]: `${clampWidth(width)}px`,
        ['--sidebar-panel-open-width' as string]: `${clampWidth(width)}px`,
      }}
      aria-hidden={!open}
    >
      {open ? (
        <div
          className="sidebar-panel__handle"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize sidebar"
          aria-valuenow={width}
          aria-valuemin={MIN_WIDTH}
          aria-valuemax={MAX_WIDTH}
          tabIndex={0}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onKeyDown={(event) => {
            if (event.key === 'ArrowLeft') {
              event.preventDefault()
              setWidth(width + 24)
            } else if (event.key === 'ArrowRight') {
              event.preventDefault()
              setWidth(width - 24)
            } else if (event.key === 'Home') {
              event.preventDefault()
              setWidth(MIN_WIDTH)
            } else if (event.key === 'End') {
              event.preventDefault()
              setWidth(MAX_WIDTH)
            }
          }}
        />
      ) : null}
      <div className="sidebar-panel__inner">{children}</div>
    </aside>
  )
}
