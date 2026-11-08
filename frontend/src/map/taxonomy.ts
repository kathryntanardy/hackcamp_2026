/** F15 repo categories (gold.category). */
export const REPO_CATEGORIES = [
  'Front-end',
  'Back-end',
  'Machine learning',
  'Database',
  'Hardware/embedded',
  'DevOps & infra',
  'other',
] as const

export type RepoCategory = (typeof REPO_CATEGORIES)[number]

/** F15 CWE vulnerability buckets (gold.vuln_buckets). */
export const VULN_BUCKETS = [
  'Code execution',
  'Unsafe deserialization',
  'Memory safety',
  'Injection',
  'Path traversal & file access',
  'Prototype pollution',
  'Denial of service',
  'Data exposure',
  'Network & TLS',
  'Auth & access control',
  'Other / unclassified',
  'No GitHub advisories',
] as const

export type VulnBucket = (typeof VULN_BUCKETS)[number]

export type ClusterMode = 'flowers' | 'language' | 'category'

export const CLUSTER_MODES: { id: ClusterMode; label: string }[] = [
  { id: 'flowers', label: 'Vulnerabilities' },
  { id: 'language', label: 'Language' },
  { id: 'category', label: 'Category' },
]
