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
const { reconcileFlowerPresence, advanceFlowerPresence, branchOpacities, flowerSlotOpacities, FLOWER_FADE_MS } =
  require('../src/map/flowerPresence.ts')
const flower = { id: 'Memory safety', colorIndex: 7 }
const repo = { id: 'repo/memory', flowerId: flower.id }

test('a removed flower retains its marks while its two branches fade, then all are removed', () => {
  const shown = reconcileFlowerPresence([], [repo], [flower], 0, true)
  const leaving = reconcileFlowerPresence(shown, [], [], 10)
  const middle = advanceFlowerPresence(leaving, 10 + FLOWER_FADE_MS / 2)
  assert.equal(middle[0].opacity, 0.5)
  assert.deepEqual(middle[0].repos, [repo])
  assert.equal(branchOpacities(middle)[4], 0.5)
  assert.equal(branchOpacities(middle)[8], 0.5)
  const gone = advanceFlowerPresence(middle, 10 + FLOWER_FADE_MS)
  assert.deepEqual(gone, [])
  assert(branchOpacities(gone).every((alpha) => alpha === 0))
})

test('reappearing mid-fade reverses smoothly and restores both branches', () => {
  const shown = reconcileFlowerPresence([], [repo], [flower], 0, true)
  const leaving = reconcileFlowerPresence(shown, [], [], 10)
  const restored = reconcileFlowerPresence(leaving, [repo], [flower], 10 + FLOWER_FADE_MS / 2)
  assert.equal(restored.length, 1)
  assert.equal(restored[0].opacity, 0.5)
  const done = advanceFlowerPresence(restored, 10 + FLOWER_FADE_MS * 1.5)
  assert.equal(done[0].opacity, 1)
  assert.equal(branchOpacities(done)[4], 1)
  assert.equal(branchOpacities(done)[8], 1)
})

test('seven category flowers leave no orphan memory stem and keep the shared right trunk', () => {
  const categories = Array.from({ length: 7 }, (_, colorIndex) => ({ id: `Category ${colorIndex}`, colorIndex }))
  const shown = reconcileFlowerPresence([], [], categories, 0, true)
  assert.equal(branchOpacities(shown)[4], 0)
  assert.equal(branchOpacities(shown)[8], 0)
  assert.equal(branchOpacities(shown)[9], 1)
  assert.equal(branchOpacities(shown)[5], 1)
  assert.equal(branchOpacities(shown.filter((entry) => entry.flower.colorIndex !== 5))[5], 1)
})

test('reduced motion applies appearance and disappearance immediately', () => {
  const shown = reconcileFlowerPresence([], [repo], [flower], 0, true)
  assert.equal(shown[0].opacity, 1)
  assert.deepEqual(reconcileFlowerPresence(shown, [], [], 1, true), [])
})

test('changing a label keeps reused petals and branches at full opacity throughout the transition', () => {
  const shown = reconcileFlowerPresence([], [repo], [flower], 0, true)
  const renamed = { ...flower, id: 'Back-end' }
  const changing = reconcileFlowerPresence(shown, [{ ...repo, flowerId: renamed.id }], [renamed], 10)
  for (const elapsed of [0, 90, 180, 270, 360]) {
    const frame = advanceFlowerPresence(changing, 10 + elapsed)
    assert.equal(flowerSlotOpacities(frame).get(7), 1)
    assert.equal(branchOpacities(frame)[4], 1)
    assert.equal(branchOpacities(frame)[8], 1)
  }
})
