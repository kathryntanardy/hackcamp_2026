import bloomUrl from '../assets/flowers/bloom.png'
import type { Point } from './types'

/** Figma flower bloom (40:17144) raster size + optical center. */
const BLOOM_W = 1033
const BLOOM_H = 771
const BLOOM_CX = BLOOM_W / 2
const BLOOM_CY = BLOOM_H / 2

/** Hue shift from Figma blue (#3991FC) toward each palette glyph. */
const HUE_SHIFT = [0, 18, 155, 175, 45, 265, 210] as const
const PALETTE_LEN = HUE_SHIFT.length

let bloomImage: HTMLImageElement | null = null
let bloomPromise: Promise<HTMLImageElement> | null = null
const tintCache = new Map<number, HTMLCanvasElement>()

function loadBloom(): Promise<HTMLImageElement> {
  if (bloomImage?.complete && bloomImage.naturalWidth > 0) {
    return Promise.resolve(bloomImage)
  }
  if (bloomPromise) return bloomPromise
  bloomPromise = new Promise((resolve, reject) => {
    const img = new Image()
    img.decoding = 'async'
    img.onload = () => {
      bloomImage = img
      resolve(img)
    }
    img.onerror = () => {
      bloomPromise = null
      reject(new Error('Failed to load flower bloom asset'))
    }
    img.src = bloomUrl
  })
  return bloomPromise
}

/** Kick off bloom load early so the first paint can use it. */
export function prefetchFlowerBloom(): void {
  void loadBloom().catch(() => {})
}

function tintedBloom(colorIndex: number): HTMLCanvasElement | HTMLImageElement | null {
  const img = bloomImage
  if (!img?.complete || img.naturalWidth === 0) return null

  const index = ((colorIndex % PALETTE_LEN) + PALETTE_LEN) % PALETTE_LEN
  if (index === 0) return img

  const cached = tintCache.get(index)
  if (cached) return cached

  const canvas = document.createElement('canvas')
  canvas.width = img.naturalWidth || BLOOM_W
  canvas.height = img.naturalHeight || BLOOM_H
  const ctx = canvas.getContext('2d')
  if (!ctx) return img

  const hue = HUE_SHIFT[index] ?? 0
  ctx.filter = `hue-rotate(${hue}deg) saturate(1.05)`
  ctx.drawImage(img, 0, 0)
  ctx.filter = 'none'
  tintCache.set(index, canvas)
  return canvas
}

/**
 * Draw the Figma soft-petal bloom centered on a flower.
 * World radius maps to the bloom's half-height (soft edges included).
 */
export function drawFlowerBloom(
  ctx: CanvasRenderingContext2D,
  center: Point,
  radius: number,
  colorIndex: number,
  scale: number,
  alpha = 1,
): void {
  const source = tintedBloom(colorIndex)
  if (!source) {
    void loadBloom().catch(() => {})
    return
  }

  const screenH = radius * scale * 2.55
  const screenW = screenH * (BLOOM_W / BLOOM_H)
  const ox = (BLOOM_CX / BLOOM_W) * screenW
  const oy = (BLOOM_CY / BLOOM_H) * screenH

  ctx.save()
  ctx.globalAlpha = alpha
  ctx.drawImage(source, center.x - ox, center.y - oy, screenW, screenH)
  ctx.restore()
}
