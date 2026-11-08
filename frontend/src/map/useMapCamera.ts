import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  MAX_SCALE,
  ZOOM_STEP,
  boundsOf,
  clampScale,
  contentCenter,
  fitBounds,
  focusOn,
  lerpCamera,
  maxScaleForViewport,
  minScaleForViewport,
  zoomForViewport,
  panBy,
  zoomAt,
  type ViewInsets,
} from './camera'
import type { MapCamera, MapRepo, Point, WorldBounds } from './types'

export type { ViewInsets }

export { worldToScreen, screenToWorld } from './camera'

const DEFAULT_CAMERA: MapCamera = { scale: 1, offsetX: 0, offsetY: 0 }
const FOCUS_DURATION_MS = 450

export function useMapCamera() {
  const [camera, setCamera] = useState<MapCamera>(DEFAULT_CAMERA)
  const fittedKey = useRef<string | null>(null)
  const viewport = useRef({ width: 1, height: 1 })
  const [viewportSize, setViewportState] = useState(viewport.current)
  const framing = useRef<{ bounds: WorldBounds; padding: number } | null>(null)
  const cameraRef = useRef(camera)
  cameraRef.current = camera

  const anim = useRef<{
    from: MapCamera
    to: MapCamera
    start: number
    duration: number
  } | null>(null)
  const raf = useRef(0)

  const stopAnim = useCallback(() => {
    if (raf.current) cancelAnimationFrame(raf.current)
    raf.current = 0
    anim.current = null
  }, [])

  useEffect(() => () => stopAnim(), [stopAnim])

  // Also bring an already-open preview within the cap after a renderer update.
  useEffect(() => {
    const { width, height } = viewport.current
    if (width > 1 && height > 1) {
      setCamera((prev) => zoomAt(prev, contentCenter(width, height), prev.scale, maxScaleForViewport(width, height), minScaleForViewport(width, height)))
    }
  }, [])

  const runAnim = useCallback(() => {
    const step = (now: number) => {
      const current = anim.current
      if (!current) return
      const t = (now - current.start) / current.duration
      const { width, height } = viewport.current
      const ceiling = maxScaleForViewport(width, height)
      if (t >= 1) {
        setCamera(zoomAt(current.to, contentCenter(width, height), current.to.scale, ceiling, minScaleForViewport(width, height)))
        anim.current = null
        raf.current = 0
        return
      }
      setCamera(lerpCamera(current.from, current.to, t, ceiling, minScaleForViewport(width, height)))
      raf.current = requestAnimationFrame(step)
    }
    if (raf.current) cancelAnimationFrame(raf.current)
    raf.current = requestAnimationFrame(step)
  }, [])

  const animateTo = useCallback(
    (to: MapCamera, duration = FOCUS_DURATION_MS) => {
      anim.current = {
        from: { ...cameraRef.current },
        to: { ...to, scale: clampScale(to.scale, maxScaleForViewport(viewport.current.width, viewport.current.height), minScaleForViewport(viewport.current.width, viewport.current.height)) },
        start: performance.now(),
        duration,
      }
      runAnim()
    },
    [runAnim],
  )

  const setViewportSize = useCallback((width: number, height: number) => {
    if (viewport.current.width === width && viewport.current.height === height) return
    const previous = viewport.current
    viewport.current = { width: Math.max(1, width), height: Math.max(1, height) }
    setViewportState(viewport.current)
    setCamera((prev) => {
      const ceiling = maxScaleForViewport(width, height)
      const frame = framing.current
      if (frame) {
        const target = fitBounds(frame.bounds, width, height, frame.padding)
        if (anim.current) {
          anim.current.to = target
          return zoomAt(prev, contentCenter(width, height), prev.scale, ceiling, minScaleForViewport(width, height))
        }
        return target
      }
      const center = contentCenter(previous.width, previous.height)
      const resized = zoomAt(prev, center, prev.scale, ceiling, minScaleForViewport(width, height))
      return panBy(resized, (width - previous.width) / 2, (height - previous.height) / 2)
    })
  }, [])

  const fitToRepos = useCallback(
    (repos: Pick<MapRepo, 'x' | 'y'>[], force = false, padding = 56) => {
      const { width, height } = viewport.current
      if (width <= 1 || height <= 1) return
      const bounds = boundsOf(repos)
      if (!bounds) return
      // Resizing uses the stored framing; don't replace a focused flower with
      // the overview just because the observer reported a different viewport.
      const key = `${repos.length}:${bounds.minX}:${bounds.maxX}:${bounds.minY}:${bounds.maxY}`
      if (!force && fittedKey.current === key) return
      fittedKey.current = key
      framing.current = { bounds, padding }
      stopAnim()
      setCamera(fitBounds(bounds, width, height, padding))
    },
    [stopAnim],
  )

  const zoomIn = useCallback(
    (anchor?: Point) => {
      stopAnim()
      framing.current = null
      setCamera((prev) => {
        const { width, height } = viewport.current
        const screen = anchor ?? contentCenter(width, height)
        return zoomForViewport(prev, screen, prev.scale * ZOOM_STEP, width, height)
      })
    },
    [stopAnim],
  )

  const zoomOut = useCallback(
    (anchor?: Point) => {
      stopAnim()
      framing.current = null
      setCamera((prev) => {
        const { width, height } = viewport.current
        const screen = anchor ?? contentCenter(width, height)
        return zoomForViewport(prev, screen, prev.scale / ZOOM_STEP, width, height)
      })
    },
    [stopAnim],
  )

  const zoomByFactor = useCallback(
    (factor: number, anchor: Point) => {
      stopAnim()
      framing.current = null
      setCamera((prev) => zoomForViewport(prev, anchor, prev.scale * factor,
        viewport.current.width, viewport.current.height))
    },
    [stopAnim],
  )

  const pan = useCallback(
    (dx: number, dy: number) => {
      stopAnim()
      framing.current = null
      setCamera((prev) => panBy(prev, dx, dy))
    },
    [stopAnim],
  )

  /**
   * Smoothly center + zoom onto a world-space point (e.g. a clicked repo).
   * Pass `insets.right` when the sidebar is about to open so the target lands
   * in the remaining map, not under the panel.
   */
  const focusOnPoint = useCallback(
    (point: Point, insets?: ViewInsets) => {
      const { width, height } = viewport.current
      if (width <= 1 || height <= 1) return

      framing.current = null
      animateTo(
        focusOn(point, width, height, MAX_SCALE, insets),
      )
    },
    [animateTo],
  )

  /** Animate camera so the given world bounds (e.g. an entire flower) fill the view. */
  const fitToBoundsAnimated = useCallback(
    (bounds: WorldBounds, padding = 72, insets?: ViewInsets) => {
      const { width, height } = viewport.current
      if (width <= 1 || height <= 1) return
      framing.current = { bounds, padding }
      animateTo(fitBounds(bounds, width, height, padding, insets), 520)
    },
    [animateTo],
  )

  return useMemo(
    () => ({
      camera,
      maxScale: maxScaleForViewport(viewportSize.width, viewportSize.height),
      minScale: minScaleForViewport(viewportSize.width, viewportSize.height),
      setCamera,
      setViewportSize,
      fitToRepos,
      fitToBoundsAnimated,
      zoomIn,
      zoomOut,
      zoomByFactor,
      pan,
      focusOnPoint,
    }),
    [
      camera,
      viewportSize,
      fitToBoundsAnimated,
      fitToRepos,
      focusOnPoint,
      pan,
      setViewportSize,
      zoomByFactor,
      zoomIn,
      zoomOut,
    ],
  )
}
