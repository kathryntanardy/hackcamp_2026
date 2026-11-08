import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from 'react'
import { worldToScreen } from '../map/camera'
import { drawMap, hitTest } from '../map/draw'
import { prefetchFlowerBloom } from '../map/flowerBloom'
import type {
  FlowerCluster,
  SeverityFocus,
  VulnSeverity,
} from '../map/flowers'
import type { MapCamera, MapRepo } from '../map/types'
import { FlowerLabel } from './FlowerLabel'
import { MapHoverCard } from './MapHoverCard'

export type GalaxyMapProps = {
  repos: MapRepo[]
  flowers: FlowerCluster[]
  camera: MapCamera
  selectedId?: string | null
  /** When set, non-matching nodes (and empty flowers) are dimmed. */
  matchIds?: ReadonlySet<string> | null
  pinnedSeverity?: SeverityFocus | null
  onSelectRepo?: (id: string) => void
  onPinnedSeverityChange?: (focus: SeverityFocus | null) => void
  /** Empty-map click (not a drag). Parent should close the sidebar. */
  onBackgroundClick?: () => void
  onViewportChange?: (width: number, height: number) => void
  onPan?: (dx: number, dy: number) => void
  onZoomByFactor?: (factor: number, anchor: { x: number; y: number }) => void
  onZoomToFlower?: (flower: FlowerCluster, tone?: VulnSeverity | null) => void
}

type HoverCard = {
  repo: MapRepo
  x: number
  y: number
}

const HOVER_LERP_UP = 10
const HOVER_LERP_DOWN = 7

export function GalaxyMap({
  repos,
  flowers,
  camera,
  selectedId = null,
  matchIds = null,
  pinnedSeverity = null,
  onSelectRepo,
  onPinnedSeverityChange,
  onBackgroundClick,
  onViewportChange,
  onPan,
  onZoomByFactor,
  onZoomToFlower,
}: GalaxyMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sizeRef = useRef({ width: 1, height: 1 })
  const [hoverCard, setHoverCard] = useState<HoverCard | null>(null)
  const [hoverSeverity, setHoverSeverity] = useState<SeverityFocus | null>(null)
  const severityFocus = hoverSeverity ?? pinnedSeverity

  const reposRef = useRef(repos)
  const flowersRef = useRef(flowers)
  const cameraRef = useRef(camera)
  const selectedRef = useRef(selectedId)
  const matchIdsRef = useRef(matchIds)
  const severityRef = useRef(severityFocus)
  reposRef.current = repos
  flowersRef.current = flowers
  cameraRef.current = camera
  selectedRef.current = selectedId
  matchIdsRef.current = matchIds
  severityRef.current = severityFocus

  useEffect(() => {
    prefetchFlowerBloom()
  }, [])

  const hoverTargetId = useRef<string | null>(null)
  const hoverAmount = useRef(0)
  const hoverRepoRef = useRef<MapRepo | null>(null)
  const drag = useRef<{
    pointerId: number
    lastX: number
    lastY: number
    moved: boolean
  } | null>(null)

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
      }
    }

    syncSize()
    const observer = new ResizeObserver(syncSize)
    observer.observe(el)
    return () => observer.disconnect()
  }, [onViewportChange])

  useEffect(() => {
    let frame = 0
    let last = performance.now()

    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now

      // Keep neighbours pushed out while a repo is selected, not only on hover.
      const target = hoverTargetId.current || selectedRef.current ? 1 : 0
      const rate = target > hoverAmount.current ? HOVER_LERP_UP : HOVER_LERP_DOWN
      const next =
        hoverAmount.current + (target - hoverAmount.current) * (1 - Math.exp(-rate * dt))
      hoverAmount.current = Math.abs(next - target) < 0.001 ? target : next

      if (!hoverTargetId.current && !selectedRef.current && hoverAmount.current < 0.01) {
        hoverAmount.current = 0
        hoverRepoRef.current = null
      }

      const canvas = canvasRef.current
      if (canvas) {
        const ctx = canvas.getContext('2d')
        if (ctx) {
          const { width, height } = sizeRef.current
          const dpr = window.devicePixelRatio || 1
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
          drawMap(
            ctx,
            reposRef.current,
            flowersRef.current,
            cameraRef.current,
            selectedRef.current,
            hoverRepoRef.current?.id ?? hoverTargetId.current,
            hoverAmount.current,
            width,
            height,
            now,
            severityRef.current,
            matchIdsRef.current,
          )
        }
      }

      frame = requestAnimationFrame(tick)
    }

    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [])

  function localPoint(event: { clientX: number; clientY: number }) {
    const el = containerRef.current
    if (!el) return { x: 0, y: 0 }
    const rect = el.getBoundingClientRect()
    return { x: event.clientX - rect.left, y: event.clientY - rect.top }
  }

  function clearHover() {
    hoverTargetId.current = null
    setHoverCard(null)
  }

  function setHoverFromHit(hit: MapRepo, point: { x: number; y: number }) {
    hoverTargetId.current = hit.id
    hoverRepoRef.current = hit
    const cardW = 260
    const cardH = 120
    const { width, height } = sizeRef.current
    let x = point.x + 16
    let y = point.y + 16
    if (x + cardW > width - 8) x = Math.max(8, point.x - cardW - 12)
    if (y + cardH > height - 8) y = Math.max(8, point.y - cardH - 12)
    setHoverCard({ repo: hit, x, y })
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
        clearHover()
      }
      return
    }

    const hit = hitTest(reposRef.current, cameraRef.current, point.x, point.y)
    if (!hit) {
      clearHover()
      return
    }
    setHoverFromHit(hit, point)
  }

  function endDrag(event: ReactPointerEvent<HTMLCanvasElement>) {
    const active = drag.current
    if (!active || active.pointerId !== event.pointerId) return
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    if (!active.moved) {
      const point = localPoint(event)
      const hit = hitTest(reposRef.current, cameraRef.current, point.x, point.y)
      if (hit) {
        setHoverSeverity(null)
        onSelectRepo?.(hit.id)
      } else {
        // Click empty map: clear filters and let parent close the sidebar.
        // Drags never reach here (active.moved).
        setHoverSeverity(null)
        onPinnedSeverityChange?.(null)
        onBackgroundClick?.()
      }
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
          if (!drag.current) clearHover()
        }}
        onWheel={onWheel}
        onContextMenu={(event) => event.preventDefault()}
        onDragStart={(event) => event.preventDefault()}
        draggable={false}
      />
      {flowers.map((flower) => {
        const screen = worldToScreen(flower.center, camera)
        const labelY = screen.y + flower.radius * camera.scale + 18
        return (
          <FlowerLabel
            key={flower.id}
            flower={flower}
            x={screen.x}
            y={labelY}
            activeTone={
              severityFocus?.flowerId === flower.id ? severityFocus.tone : null
            }
            categoryActive={
              pinnedSeverity?.flowerId === flower.id && pinnedSeverity.tone == null
            }
            onHoverTone={(tone) => {
              setHoverSeverity(tone ? { flowerId: flower.id, tone } : null)
            }}
            onFocusFlower={() => {
              const same =
                pinnedSeverity?.flowerId === flower.id && pinnedSeverity.tone == null
              const next: SeverityFocus | null = same
                ? null
                : { flowerId: flower.id, tone: null }
              setHoverSeverity(null)
              onPinnedSeverityChange?.(next)
              if (next) onZoomToFlower?.(flower, null)
            }}
            onSelectTone={(tone) => {
              const same =
                pinnedSeverity?.flowerId === flower.id &&
                pinnedSeverity?.tone === tone
              const next = same ? null : { flowerId: flower.id, tone }
              onPinnedSeverityChange?.(next)
              setHoverSeverity(next)
              // Always frame the whole flower, even when clearing a tone pin.
              onZoomToFlower?.(flower, tone)
            }}
          />
        )
      })}
      {hoverCard ? (
        <MapHoverCard repo={hoverCard.repo} x={hoverCard.x} y={hoverCard.y} />
      ) : null}
    </div>
  )
}
