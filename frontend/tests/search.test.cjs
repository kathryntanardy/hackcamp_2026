const assert = require('node:assert/strict')
const fs = require('node:fs')
const { test } = require('node:test')
const ts = require('typescript')

// Run the actual TypeScript helpers with Node's built-in test runner.
require.extensions['.ts'] = (module, filename) => {
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  })
  module._compile(outputText, filename)
}

const { localSearchIds, mergeSearchIds, searchResultItems } = require('../src/map/search.ts')
const { layoutFlowerMap } = require('../src/map/flowers.ts')
const { fetchFindings } = require('../src/api/findings.ts')
const { fetchSearch } = require('../src/api/search.ts')

const repos = [
  { id: 'owner/http', name: 'http', category: 'Back-end', language: 'Python',
    overview: 'An HTTP client', vulnBuckets: ['Network & TLS'], importance: 4, vulnerabilityTone: 'low' },
  { id: 'owner/sql', name: 'sql', category: 'Database', language: 'Rust',
    overview: 'Stores React examples', vulnBuckets: ['Memory safety', 'Injection'], importance: 2, vulnerabilityTone: 'high' },
  { id: 'owner/ui', name: 'ui', category: 'Front-end', language: 'JavaScript',
    overview: 'Browser components', vulnBuckets: [], importance: 3, vulnerabilityTone: 'medium' },
]
const list = repos.map((repo) => ({ id: repo.id, name: repo.name, category: repo.category, description: repo.overview }))

test('grouping fields and repository scope keep their matches', () => {
  assert.deepEqual(localSearchIds('database', repos, list, 'category'), ['owner/sql'])
  assert.deepEqual(localSearchIds('React', repos, list, 'category'), [])
  assert.deepEqual(localSearchIds('MEMORY', repos, list, 'vulnerabilities'), ['owner/sql'])
  assert.deepEqual(localSearchIds('injection', repos, list, 'vulnerabilities'), ['owner/sql'])
  assert.deepEqual(localSearchIds('owner/http', repos, list, 'name'), ['owner/http'])
  assert.deepEqual(localSearchIds('Rust', repos, list, 'all'), ['owner/sql'])
  assert.deepEqual(localSearchIds('does not exist', repos, list, 'all'), [])
})

test('rea finds React first in every grouping, even before an overview containing increase', () => {
  const corpus = [
    { ...repos[0], id: 'other/project', name: 'project', overview: 'Release activity increased' },
    { ...repos[2], id: 'facebook/react', name: 'react' },
    { ...repos[2], id: 'owner/react-native', name: 'react-native' },
  ]
  for (const scope of ['all', 'category', 'vulnerabilities', 'name']) {
    const ids = localSearchIds('ReA', corpus, [], scope)
    assert.equal(ids[0], 'facebook/react')
    assert.equal(ids[1], 'owner/react-native')
  }
  const localIds = localSearchIds('rea', corpus, [], 'all')
  assert.deepEqual(mergeSearchIds('rea', corpus, localIds, ['other/project', 'missing/repo']),
    ['facebook/react', 'owner/react-native', 'other/project'])
  assert.deepEqual(mergeSearchIds('rea', corpus, localIds, []), localIds)
})

test('autocomplete preserves semantic rank and includes results beyond the first eight', () => {
  assert.deepEqual(searchResultItems(list, ['owner/sql', 'owner/http', 'unknown', 'owner/sql'])
    .map((repo) => repo.id), ['owner/sql', 'owner/http'])
  assert.deepEqual(searchResultItems(list, null), [])
  const many = Array.from({ length: 12 }, (_, i) => ({ ...list[0], id: `repo/${i}` }))
  assert.deepEqual(searchResultItems(many, ['repo/11', 'repo/2']).map((repo) => repo.id),
    ['repo/11', 'repo/2'])
})

const corpus = Array.from({ length: 12 }, (_, group) =>
  Array.from({ length: 13 - group }, (_, item) => ({
    ...repos[0], id: `${group}/${item}`, vulnBuckets: [`Bucket ${group}`],
  }))).flat()

test('search brings a hidden bucket into the existing artwork without moving retained flowers', () => {
  const overview = layoutFlowerMap(corpus)
  assert.equal(overview.flowers.length, 8)
  assert(!overview.repos.some((repo) => repo.id === '11/0'))
  const searched = layoutFlowerMap(corpus, new Set(['11/0']))
  assert.equal(searched.flowers.length, 8)
  assert(searched.repos.some((repo) => repo.id === '11/0'))
  for (const flower of searched.flowers) {
    const original = overview.flowers.find((item) => item.id === flower.id)
    if (original) assert.deepEqual(flower.center, original.center)
  }
  assert.deepEqual(layoutFlowerMap(corpus), overview)
})

test('a selected finding can reveal its repo even when search prefers eight other groups', () => {
  const priorities = new Set(['11/0', ...Array.from({ length: 8 }, (_, group) => `${group}/0`)])
  assert(layoutFlowerMap(corpus, priorities).repos.some((repo) => repo.id === '11/0'))
})

test('Category replaces flower labels and x membership with project categories', () => {
  const grouped = layoutFlowerMap(repos, null, 'category')
  assert.deepEqual(new Set(grouped.flowers.map((flower) => flower.label)),
    new Set(['Back-end', 'Database', 'Front-end']))
  assert.equal(grouped.repos.length, repos.length)
  for (const flower of grouped.flowers) {
    const expected = repos.filter((repo) => repo.category === flower.label).map((repo) => repo.id)
    assert.deepEqual(flower.repoIds, expected)
    assert(grouped.repos.filter((repo) => repo.flowerId === flower.id)
      .every((repo) => repo.category === flower.label))
  }
})

test('switching back to Vulnerabilities restores bucket labels and x membership', () => {
  const grouped = layoutFlowerMap(repos, null, 'vulnerabilities')
  assert.deepEqual(new Set(grouped.flowers.map((flower) => flower.label)),
    new Set(['Network & TLS', 'Memory safety', 'No GitHub advisories']))
  assert.equal(grouped.repos.length, repos.length)
})

test('Findings keeps incoming category, bucket, language, risk, sort and pagination parameters', async () => {
  const original = global.fetch
  const controller = new AbortController()
  try {
    global.fetch = async (url, options) => {
      const query = new URL(url, 'http://localhost').searchParams
      assert.equal(query.get('category'), 'Database')
      assert.equal(query.get('vuln_bucket'), 'Memory safety')
      assert.equal(query.get('language'), 'Rust')
      assert.equal(query.get('risk'), 'at_risk')
      assert.equal(query.get('sort'), 'max_cvss')
      assert.equal(query.get('limit'), '50')
      assert.equal(query.get('offset'), '50')
      assert.equal(options.signal, controller.signal)
      return { ok: true, json: async () => ({ items: [], total: 0 }) }
    }
    await fetchFindings({ category: 'Database', vuln_bucket: 'Memory safety', language: 'Rust',
      risk: 'at_risk', sort: 'max_cvss', limit: 50, offset: 50 }, controller.signal)
  } finally { global.fetch = original }
})

test('natural-language search still uses the incoming API with its abort signal', async () => {
  const original = global.fetch
  const controller = new AbortController()
  try {
    global.fetch = async (url, options) => {
      assert.equal(new URL(url, 'http://localhost').searchParams.get('q'), 'python HTTP clients')
      assert.equal(options.signal, controller.signal)
      return { ok: true, json: async () => ({ query: 'python HTTP clients', repo_ids: ['owner/http'] }) }
    }
    assert.deepEqual((await fetchSearch({ q: 'python HTTP clients' }, controller.signal)).repo_ids, ['owner/http'])
  } finally { global.fetch = original }
})
