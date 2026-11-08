import { branchArtwork, flowerArtwork } from './flowerArtwork'
import { CENTRAL_BRANCH_JUNCTION_Y } from './flowerPresence'
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
const branches = new Map<number, Bloom>()
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
      branchArtwork.forEach((branch, i) => {
        const asset = images[i]
        const [a, b, c, d, tx, ty] = branch.matrix
        const offset = branch.offset
        const corners = [[0, 0], [asset.naturalWidth, 0], [0, asset.naturalHeight],
          [asset.naturalWidth, asset.naturalHeight]].map(([x, y]) => ({
            x: a * (x + offset.x) + c * (y + offset.y) + tx,
            y: b * (x + offset.x) + d * (y + offset.y) + ty,
          }))
        const x = Math.floor(Math.min(...corners.map((p) => p.x)))
        const y = Math.floor(Math.min(...corners.map((p) => p.y)))
        const width = Math.ceil(Math.max(...corners.map((p) => p.x))) - x
        const height = Math.ceil(Math.max(...corners.map((p) => p.y))) - y
        const image = createCanvas(width, height)
        const ctx = image.getContext('2d')
        if (!ctx) return
        ctx.scale(RESOLUTION, RESOLUTION)
        ctx.translate(-x, -y)
        drawAsset(ctx, branch, asset)
        branches.set(i, { image, x, y, width, height })
      })
    })(),
  ]).then(() => undefined).catch(() => { loading = null })
}

export function drawFlowerBranches(
  ctx: CanvasRenderingContext2D, camera: MapCamera, opacities: readonly number[],
): void {
  ctx.save()
  ctx.translate(camera.offsetX, camera.offsetY)
  ctx.scale(camera.scale, camera.scale)
  branches.forEach((branch, i) => {
    if (i === 4) {
      // Remove the upper flower's own stem while keeping the trunk below the
      // magenta junction connected to its remaining flower.
      for (const [alpha, y, height] of [
        [opacities[4] ?? 0, branch.y, CENTRAL_BRANCH_JUNCTION_Y - branch.y],
        [opacities[9] ?? 0, CENTRAL_BRANCH_JUNCTION_Y, branch.y + branch.height - CENTRAL_BRANCH_JUNCTION_Y],
      ]) {
        if (alpha <= 0) continue
        ctx.save()
        ctx.globalAlpha = alpha
        ctx.beginPath()
        ctx.rect(branch.x, y, branch.width, height)
        ctx.clip()
        ctx.drawImage(branch.image, branch.x, branch.y, branch.width, branch.height)
        ctx.restore()
      }
      return
    }
    ctx.globalAlpha = opacities[i] ?? 0
    if (ctx.globalAlpha > 0) {
      ctx.drawImage(branch.image, branch.x, branch.y, branch.width, branch.height)
    }
  })
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
