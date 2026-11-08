import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from 'react'
import { drawMap, hitTest } from '../map/draw'
import type { MapCamera, MapRepo } from '../map/types'
import { MapHoverCard } from './MapHoverCard'

export type GalaxyMapProps = {
  repos: MapRepo[]
  camera: MapCamera
  selectedId?: string | null
  onSelectRepo?: (id: string) => void
  onViewportChange?: (width: number, height: number) => void
  onPan?: (dx: number, dy: number) => void
  onZoomByFactor?: (factor: number, anchor: { x: number; y: number }) => void
}

type HoverState = {
  repo: MapRepo
  x: number
  y: number
}

export function GalaxyMap({
  repos,
  camera,
  selectedId = null,
  onSelectRepo,
  onViewportChange,
  onPan,
  onZoomByFactor,
}: GalaxyMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sizeRef = useRef({ width: 1, height: 1 })
  const [sizeVersion, setSizeVersion] = useState(0)
  const [hover, setHover] = useState<HoverState | null>(null)
  const drag = useRef<{
    pointerId: number
    lastX: number
    lastY: number
    moved: boolean
  } | null>(null)

  // Keep canvas buffer sized to the pane; notify parent of viewport for camera fit.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const syncSize = () => {
      const rect = el.getBoundingClientRect()
      const width = Math.max(1, Math.floor(rect.width))
      const height = Math.max(1, Math.floor(rect.height))
      sizeRef.current = { width, height }
      onViewportChange?.(width, height)

      const canvas = canvasRef.current
      if (!canvas) return
      const dpr = window.devicePixelRatio || 1
      const nextW = Math.floor(width * dpr)
      const nextH = Math.floor(height * dpr)
      if (canvas.width !== nextW || canvas.height !== nextH) {
        canvas.width = nextW
        canvas.height = nextH
        canvas.style.width = `${width}px`
        canvas.style.height = `${height}px`
        setSizeVersion((v) => v + 1)
      }
    }

    syncSize()
    const observer = new ResizeObserver(syncSize)
    observer.observe(el)
    return () => observer.disconnect()
  }, [onViewportChange])

  useLayoutEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const { width, height } = sizeRef.current
    const dpr = window.devicePixelRatio || 1
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    drawMap(ctx, repos, camera, selectedId, hover?.repo.id ?? null, width, height)
  }, [camera, hover?.repo.id, repos, selectedId, sizeVersion])

  function localPoint(event: { clientX: number; clientY: number }) {
    const el = containerRef.current
    if (!el) return { x: 0, y: 0 }
    const rect = el.getBoundingClientRect()
    return { x: event.clientX - rect.left, y: event.clientY - rect.top }
  }

  function onPointerDown(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (event.button !== 0) return
    event.currentTarget.setPointerCapture(event.pointerId)
    const point = localPoint(event)
    drag.current = {
      pointerId: event.pointerId,
      lastX: point.x,
      lastY: point.y,
      moved: false,
    }
  }

  function onPointerMove(event: ReactPointerEvent<HTMLCanvasElement>) {
    const point = localPoint(event)
    const active = drag.current

    if (active && active.pointerId === event.pointerId) {
      const dx = point.x - active.lastX
      const dy = point.y - active.lastY
      if (Math.hypot(dx, dy) > 2) active.moved = true
      active.lastX = point.x
      active.lastY = point.y
      if (active.moved) {
        onPan?.(dx, dy)
        setHover(null)
      }
      return
    }

    const hit = hitTest(repos, camera, point.x, point.y)
    if (!hit) {
      setHover(null)
      return
    }
    const cardW = 314
    const cardH = 196
    const { width, height } = sizeRef.current
    let x = point.x + 16
    let y = point.y + 16
    if (x + cardW > width - 8) x = Math.max(8, point.x - cardW - 12)
    if (y + cardH > height - 8) y = Math.max(8, point.y - cardH - 12)
    setHover({ repo: hit, x, y })
  }

  function endDrag(event: ReactPointerEvent<HTMLCanvasElement>) {
    const active = drag.current
    if (!active || active.pointerId !== event.pointerId) return
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    if (!active.moved) {
      const point = localPoint(event)
      const hit = hitTest(repos, camera, point.x, point.y)
      if (hit) onSelectRepo?.(hit.id)
    }
    drag.current = null
  }

  function onWheel(event: ReactWheelEvent<HTMLCanvasElement>) {
    event.preventDefault()
    const point = localPoint(event)
    const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12
    onZoomByFactor?.(factor, point)
  }

  return (
    <div className="galaxy-map" ref={containerRef} aria-label="Repository galaxy map">
      <canvas
        ref={canvasRef}
        className="galaxy-map__canvas"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onPointerLeave={() => {
          if (!drag.current) setHover(null)
        }}
        onWheel={onWheel}
      />
      {hover ? <MapHoverCard repo={hover.repo} x={hover.x} y={hover.y} /> : null}
    </div>
  )
}
