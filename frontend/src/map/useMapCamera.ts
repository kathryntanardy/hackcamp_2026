import { useCallback, useMemo, useRef, useState } from 'react'
import {
  ZOOM_STEP,
  boundsOf,
  clampScale,
  fitBounds,
  panBy,
  zoomAt,
} from './camera'
import type { MapCamera, MapRepo, Point } from './types'

export { worldToScreen, screenToWorld } from './camera'

const DEFAULT_CAMERA: MapCamera = { scale: 4, offsetX: 0, offsetY: 0 }

export function useMapCamera() {
  const [camera, setCamera] = useState<MapCamera>(DEFAULT_CAMERA)
  const fittedKey = useRef<string | null>(null)
  const viewport = useRef({ width: 1, height: 1 })

  const setViewportSize = useCallback((width: number, height: number) => {
    viewport.current = { width: Math.max(1, width), height: Math.max(1, height) }
  }, [])

  const fitToRepos = useCallback((repos: Pick<MapRepo, 'x' | 'y'>[], force = false) => {
    const { width, height } = viewport.current
    if (width <= 1 || height <= 1) return
    const bounds = boundsOf(repos)
    if (!bounds) return
    const key = `${repos.length}:${bounds.minX}:${bounds.maxX}:${bounds.minY}:${bounds.maxY}:${width}x${height}`
    if (!force && fittedKey.current === key) return
    fittedKey.current = key
    setCamera(fitBounds(bounds, width, height))
  }, [])

  const zoomIn = useCallback((anchor?: Point) => {
    setCamera((prev) => {
      const { width, height } = viewport.current
      const screen = anchor ?? { x: width / 2, y: height / 2 }
      return zoomAt(prev, screen, prev.scale * ZOOM_STEP)
    })
  }, [])

  const zoomOut = useCallback((anchor?: Point) => {
    setCamera((prev) => {
      const { width, height } = viewport.current
      const screen = anchor ?? { x: width / 2, y: height / 2 }
      return zoomAt(prev, screen, prev.scale / ZOOM_STEP)
    })
  }, [])

  const zoomByFactor = useCallback((factor: number, anchor: Point) => {
    setCamera((prev) => zoomAt(prev, anchor, clampScale(prev.scale * factor)))
  }, [])

  const pan = useCallback((dx: number, dy: number) => {
    setCamera((prev) => panBy(prev, dx, dy))
  }, [])

  return useMemo(
    () => ({
      camera,
      setCamera,
      setViewportSize,
      fitToRepos,
      zoomIn,
      zoomOut,
      zoomByFactor,
      pan,
    }),
    [camera, fitToRepos, pan, setViewportSize, zoomByFactor, zoomIn, zoomOut],
  )
}
