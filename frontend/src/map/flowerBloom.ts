import { branchArtwork, flowerArtwork } from './flowerArtwork'
import { FLOWER_SCENE } from './flowerScene'
import type { MapCamera } from './types'

type Artwork = {
  src: string
  matrix: readonly number[]
  width: number
  height: number
  offset: { readonly x: number; readonly y: number } | null
}
type Bloom = { image: HTMLCanvasElement; x: number; y: number; width: number; height: number }
const blooms = new Map<number, Bloom>()
let branches: HTMLCanvasElement | null = null
let loading: Promise<void> | null = null
const RESOLUTION = 2

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = reject
    image.src = src
  })
}

function drawAsset(ctx: CanvasRenderingContext2D, item: Artwork, image: HTMLImageElement): void {
  const [a, b, c, d, x, y] = item.matrix
  ctx.save()
  ctx.transform(a, b, c, d, x, y)
  const offset = item.offset ?? {
    x: -(image.naturalWidth - item.width) / 2,
    y: -(image.naturalHeight - item.height) / 2,
  }
  // Keep each exported SVG's intrinsic dimensions, including its blur bounds.
  ctx.drawImage(image, offset.x, offset.y)
  ctx.restore()
}

function createCanvas(width: number, height: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = Math.ceil(width * RESOLUTION)
  canvas.height = Math.ceil(height * RESOLUTION)
  return canvas
}

/** Cache the exact exported layers, retaining every Figma affine transform. */
export function prefetchFlowerBloom(): void {
  if (loading) return
  loading = Promise.all([
    ...flowerArtwork.map(async ({ bounds, petals }, index) => {
      const images = await Promise.all(petals.map(petal => loadImage(petal.src)))
      const image = createCanvas(bounds.width, bounds.height)
      const ctx = image.getContext('2d')
      if (!ctx) return
      ctx.scale(RESOLUTION, RESOLUTION)
      ctx.translate(-bounds.x, -bounds.y)
      petals.forEach((petal, i) => drawAsset(ctx, petal, images[i]))
      blooms.set(index, { image, ...bounds })
    }),
    (async () => {
      const images = await Promise.all(branchArtwork.map(branch => loadImage(branch.src)))
      const image = createCanvas(FLOWER_SCENE.width, FLOWER_SCENE.height)
      const ctx = image.getContext('2d')
      if (!ctx) return
      ctx.scale(RESOLUTION, RESOLUTION)
      branchArtwork.forEach((branch, i) => drawAsset(ctx, branch, images[i]))
      branches = image
    })(),
  ]).then(() => undefined).catch(() => { loading = null })
}

export function drawFlowerBranches(ctx: CanvasRenderingContext2D, camera: MapCamera): void {
  if (!branches) return
  ctx.save()
  ctx.translate(camera.offsetX, camera.offsetY)
  ctx.scale(camera.scale, camera.scale)
  ctx.drawImage(branches, 0, 0, FLOWER_SCENE.width, FLOWER_SCENE.height)
  ctx.restore()
}

export function drawFlowerBloom(ctx: CanvasRenderingContext2D, colorIndex: number, camera: MapCamera, alpha = 1): void {
  const bloom = blooms.get(colorIndex)
  if (!bloom) { prefetchFlowerBloom(); return }
  ctx.save()
  ctx.globalAlpha = alpha
  ctx.translate(camera.offsetX, camera.offsetY)
  ctx.scale(camera.scale, camera.scale)
  ctx.drawImage(bloom.image, bloom.x, bloom.y, bloom.width, bloom.height)
  ctx.restore()
}
