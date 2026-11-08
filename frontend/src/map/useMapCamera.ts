import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  MAX_SCALE,
  MIN_SCALE,
  ZOOM_STEP,
  boundsOf,
  clampScale,
  contentCenter,
  fitBounds,
  focusOn,
  lerpCamera,
  panBy,
  zoomAt,
  type ViewInsets,
} from './camera'
import type { MapCamera, MapRepo, Point, WorldBounds } from './types'

export type { ViewInsets }

export { worldToScreen, screenToWorld } from './camera'

const DEFAULT_CAMERA: MapCamera = { scale: 4, offsetX: 0, offsetY: 0 }
const FOCUS_DURATION_MS = 450
/** Aim for ~this many pixels of glyph when focusing a node. */
const FOCUS_GLYPH_PX = 52

export function useMapCamera() {
  const [camera, setCamera] = useState<MapCamera>(DEFAULT_CAMERA)
  const fittedKey = useRef<string | null>(null)
  const viewport = useRef({ width: 1, height: 1 })
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

  const runAnim = useCallback(() => {
    const step = (now: number) => {
      const current = anim.current
      if (!current) return
      const t = (now - current.start) / current.duration
      if (t >= 1) {
        setCamera(current.to)
        anim.current = null
        raf.current = 0
        return
      }
      setCamera(lerpCamera(current.from, current.to, t))
      raf.current = requestAnimationFrame(step)
    }
    if (raf.current) cancelAnimationFrame(raf.current)
    raf.current = requestAnimationFrame(step)
  }, [])

  const animateTo = useCallback(
    (to: MapCamera, duration = FOCUS_DURATION_MS) => {
      anim.current = {
        from: { ...cameraRef.current },
        to,
        start: performance.now(),
        duration,
      }
      runAnim()
    },
    [runAnim],
  )

  const setViewportSize = useCallback((width: number, height: number) => {
    viewport.current = { width: Math.max(1, width), height: Math.max(1, height) }
  }, [])

  const fitToRepos = useCallback(
    (repos: Pick<MapRepo, 'x' | 'y'>[], force = false) => {
      const { width, height } = viewport.current
      if (width <= 1 || height <= 1) return
      const bounds = boundsOf(repos)
      if (!bounds) return
      // Key ignores viewport size so sidebar resize updates layout metrics
      // without reframing the camera.
      const key = `${repos.length}:${bounds.minX}:${bounds.maxX}:${bounds.minY}:${bounds.maxY}`
      if (!force && fittedKey.current === key) return
      fittedKey.current = key
      stopAnim()
      setCamera(fitBounds(bounds, width, height))
    },
    [stopAnim],
  )

  const zoomIn = useCallback(
    (anchor?: Point) => {
      stopAnim()
      setCamera((prev) => {
        const { width, height } = viewport.current
        const screen = anchor ?? contentCenter(width, height)
        return zoomAt(prev, screen, prev.scale * ZOOM_STEP)
      })
    },
    [stopAnim],
  )

  const zoomOut = useCallback(
    (anchor?: Point) => {
      stopAnim()
      setCamera((prev) => {
        const { width, height } = viewport.current
        const screen = anchor ?? contentCenter(width, height)
        return zoomAt(prev, screen, prev.scale / ZOOM_STEP)
      })
    },
    [stopAnim],
  )

  const zoomByFactor = useCallback(
    (factor: number, anchor: Point) => {
      stopAnim()
      setCamera((prev) => zoomAt(prev, anchor, clampScale(prev.scale * factor)))
    },
    [stopAnim],
  )

  const pan = useCallback(
    (dx: number, dy: number) => {
      stopAnim()
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
    (point: Point, importance = 1, insets?: ViewInsets) => {
      const { width, height } = viewport.current
      if (width <= 1 || height <= 1) return

      const worldSize = 2.6 + Math.min(3.4, Math.max(0, importance) * 0.7)
      const glyphScale = FOCUS_GLYPH_PX / worldSize
      const prev = cameraRef.current
      // Always zoom in at least a bit; never zoom out when focusing.
      const targetScale = clampScale(
        Math.max(prev.scale * 1.15, Math.min(MAX_SCALE * 0.55, Math.max(glyphScale, prev.scale))),
      )
      // If already very zoomed, still re-center at a modest bump.
      const scale =
        targetScale <= prev.scale * 1.02
          ? clampScale(Math.min(MAX_SCALE, prev.scale * 1.6))
          : targetScale

      animateTo(
        focusOn(point, width, height, Math.max(scale, MIN_SCALE * 4), insets),
      )
    },
    [animateTo],
  )

  /** Animate camera so the given world bounds (e.g. an entire flower) fill the view. */
  const fitToBoundsAnimated = useCallback(
    (bounds: WorldBounds, padding = 72, insets?: ViewInsets) => {
      const { width, height } = viewport.current
      if (width <= 1 || height <= 1) return
      animateTo(fitBounds(bounds, width, height, padding, insets), 520)
    },
    [animateTo],
  )

  return useMemo(
    () => ({
      camera,
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
