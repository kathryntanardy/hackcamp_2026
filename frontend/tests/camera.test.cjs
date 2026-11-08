const assert = require('node:assert/strict')
const fs = require('node:fs')
const { test } = require('node:test')
const ts = require('typescript')

require.extensions['.ts'] = (module, filename) => {
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  })
  module._compile(outputText, filename)
}
const { fitBounds, minScaleForViewport, maxScaleForViewport, zoomForViewport, focusOn, lerpCamera } = require('../src/map/camera.ts')
const bounds = { minX: 0, minY: 0, maxX: 1680, maxY: 1029 }

test('repeated zoom-out gestures stop at the full branch design on desktop, narrow screens and beside a drawer', () => {
  for (const [width, height] of [[1680, 1029], [1280, 632], [320, 550], [700, 632]]) {
    const overview = fitBounds(bounds, width, height, 0)
    let camera = zoomForViewport(overview, { x: 73, y: 45 }, overview.scale * 2, width, height)
    assert.ok(camera.scale > overview.scale)
    for (let i = 0; i < 30; i++) camera = zoomForViewport(camera, { x: 73, y: 45 }, camera.scale / 1.35, width, height)
    assert.deepEqual(camera, overview)
    assert.equal(camera.scale, minScaleForViewport(width, height))
  }
})

test('zoom-in and cursor anchoring still work between the design limits', () => {
  const width = 1280, height = 632, anchor = { x: 200, y: 180 }
  const start = fitBounds(bounds, width, height, 0)
  const zoomed = zoomForViewport(start, anchor, start.scale * 1.35, width, height)
  assert.equal((anchor.x - start.offsetX) / start.scale, (anchor.x - zoomed.offsetX) / zoomed.scale)
  const capped = zoomForViewport(start, anchor, 100, width, height)
  assert.equal(capped.scale, maxScaleForViewport(width, height))
})

test('programmatic fitting, focusing and animations respect the same minimum', () => {
  const width = 1280, height = 632, floor = minScaleForViewport(width, height)
  assert.equal(fitBounds(bounds, width, height, 500).scale, floor)
  assert.equal(focusOn({ x: 800, y: 500 }, width, height, 0.01).scale, floor)
  const from = { scale: floor, offsetX: 0, offsetY: 0 }
  assert.equal(lerpCamera(from, { ...from, scale: 0.01 }, 1, maxScaleForViewport(width, height), floor).scale, floor)
})
