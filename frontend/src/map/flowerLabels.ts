import { MAX_SCALE, worldToScreen } from './camera'
import { FLOWER_SLOTS } from './flowerScene'
import type { FlowerCluster } from './flowers'
import type { MapCamera } from './types'

/** Keep labels compact, moving them below the bloom as it fills the view. */
export function flowerLabelLayout(flower: FlowerCluster, camera: MapCamera, maxScale = MAX_SCALE) {
  const slot = FLOWER_SLOTS[flower.colorIndex]
  const scale = Math.min(1, camera.scale)
  const overview = worldToScreen(slot.label, camera)
  const bottom = worldToScreen({
    x: flower.center.x,
    y: slot.bounds.y + slot.bounds.height,
  }, camera)
  const overviewScale = Math.min(1, maxScale / 2)
  const progress = Math.min(1, Math.max(0, (camera.scale - overviewScale) / (maxScale - overviewScale)))
  // The reference label stays 196 × 63px while the bloom grows; a 14px gap
  // separates it from the artwork's blur bounds at maximum zoom.
  const targetX = bottom.x - slot.label.width * scale / 2
  const targetY = bottom.y + 14 * scale
  return {
    x: overview.x + (targetX - overview.x) * progress,
    y: overview.y + (targetY - overview.y) * progress,
    width: slot.label.width,
    scale,
  }
}
