import type { Point } from './types'

// Prefer marks 25% larger, keeping the original gap. Dense flowers scale down
// below this preferred size so the complete grid still fits its available area.
const GLYPH_SIZE = 4.727 * 1.25
const CELL_STEP = GLYPH_SIZE + 0.788
const GLYPH_RATIO = GLYPH_SIZE / CELL_STEP

/** Fill the middle row first, then balanced pairs of rows above and below it. */
export function layoutFlowerMarks(count: number, center: Point, width: number, height: number): { points: Point[]; glyphSize: number } {
  if (count <= 0) return { points: [], glyphSize: 0 }
  let rows = 1
  let columns = 1
  const capacity = () => {
    let total = columns
    for (let row = 1; row <= (rows - 1) / 2; row++) total += 2 * (columns - 2 * row)
    return total
  }
  while (capacity() < count) {
    rows += 2
    columns = 2 * rows - 1
  }
  const step = Math.min(CELL_STEP, width / (columns - 1 + GLYPH_RATIO), height / (rows - 1 + GLYPH_RATIO))
  const points: Point[] = []
  function addRow(row: number, size: number, direction: number) {
    for (let i = 0; i < size; i++) {
      const column = i === 0 ? 0 : Math.ceil(i / 2) * (i % 2 ? -1 : 1) * direction
      points.push({ x: center.x + column * step, y: center.y + row * step })
    }
  }
  addRow(0, Math.min(columns, count), 1)
  for (let row = 1; points.length < count; row++) {
    const rowCapacity = columns - 2 * row
    const remaining = count - points.length
    const above = Math.min(rowCapacity, Math.ceil(remaining / 2))
    const below = Math.min(rowCapacity, remaining - above)
    addRow(-row, above, 1)
    addRow(row, below, -1)
  }
  return { points, glyphSize: step * GLYPH_RATIO }
}
