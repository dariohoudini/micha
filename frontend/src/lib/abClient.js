/**
 * abClient — client-side A/B flag evaluation (Mobile App Engineering CH21).
 *
 * Complements lib/flags.js (server-side bucketing): this SDK evaluates
 * assignments LOCALLY against a pre-fetched experiment config —
 * zero network latency per flag check, deterministic within and across
 * sessions, and resilient to network failure (config cached in
 * localStorage; last good config keeps working offline).
 *
 * Bucketing: FNV-1a hash of (subjectId + experimentId) mod 100, exactly
 * as the doc specifies. Same user always lands in the same variant.
 *
 *   await initAB(userId)              — fetch config (falls back to cache)
 *   getVariant('exp-slug')            — variant id | null (not in traffic)
 *   getExperimentConfig('exp-slug')   — variant config object
 *   activeVariants()                  — {slug: variantId} for event schema
 *
 * Exposure logging: first getVariant() call per experiment per session
 * fires POST /api/v1/mobile/experiments/exposure/ (server bridges it
 * into flags.ExperimentExposure for the A/B evaluation jobs).
 */
import { getSessionId, setVariantsProvider } from '@/lib/eventBatch'

const CONFIG_KEY = 'micha_ab_config_v1'

let _config = null
let _subjectId = ''
let _exposed = new Set()

/* FNV-1a — fast, deterministic, well-distributed (doc CH21). */
function fnv1a(input) {
  let hash = 2166136261
  const str = String(input)
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i)
    hash = (hash * 16777619) >>> 0
  }
  return hash % 100
}

export async function initAB(userId) {
  _subjectId = userId ? String(userId) : `anon:${getSessionId()}`
  try {
    const { default: client } = await import('@/api/client')
    const platform = window.Capacitor?.getPlatform?.() || 'web'
    const { data } = await client.get(
      `/api/v1/mobile/experiments/config/?platform=${platform}`)
    _config = data
    try { localStorage.setItem(CONFIG_KEY, JSON.stringify(data)) } catch {}
  } catch {
    // Network failure → last cached config (doc: offline resilience)
    try {
      const cached = localStorage.getItem(CONFIG_KEY)
      if (cached) _config = JSON.parse(cached)
    } catch {}
  }
  setVariantsProvider(activeVariants)
  return _config
}

function findExperiment(experimentId) {
  return _config?.experiments?.find(e => e.id === experimentId) || null
}

export function getVariant(experimentId) {
  const experiment = findExperiment(experimentId)
  if (!experiment) return null

  // In experiment traffic at all?
  const bucket = fnv1a(_subjectId + experimentId)
  if (bucket >= (experiment.traffic_allocation ?? 100)) return null

  // Weighted variant assignment:
  const variantBucket = fnv1a(_subjectId + experimentId + 'variant')
  let cumWeight = 0
  let assigned = experiment.variants?.[0]?.id ?? null
  for (const variant of experiment.variants || []) {
    cumWeight += variant.weight
    if (variantBucket < cumWeight) { assigned = variant.id; break }
  }

  if (assigned && !_exposed.has(experimentId)) {
    _exposed.add(experimentId)
    logExposure(experimentId, assigned)
  }
  return assigned
}

export function getExperimentConfig(experimentId) {
  const variantId = getVariant(experimentId)
  const experiment = findExperiment(experimentId)
  const variant = experiment?.variants?.find(v => v.id === variantId)
  return variant?.config ?? {}
}

/** Current assignments — stamped onto every analytics event (CH20). */
export function activeVariants() {
  const out = {}
  for (const exp of _config?.experiments || []) {
    const v = getVariantSilent(exp.id)
    if (v) out[exp.id] = v
  }
  return out
}

/* Same math as getVariant but never logs an exposure — used by the
   event schema stamping so passive reads don't pollute exposures. */
function getVariantSilent(experimentId) {
  const experiment = findExperiment(experimentId)
  if (!experiment) return null
  if (fnv1a(_subjectId + experimentId) >=
      (experiment.traffic_allocation ?? 100)) return null
  const variantBucket = fnv1a(_subjectId + experimentId + 'variant')
  let cumWeight = 0
  for (const variant of experiment.variants || []) {
    cumWeight += variant.weight
    if (variantBucket < cumWeight) return variant.id
  }
  return experiment.variants?.[0]?.id ?? null
}

async function logExposure(experimentId, variantId) {
  try {
    const { default: client } = await import('@/api/client')
    await client.post('/api/v1/mobile/experiments/exposure/', {
      experiment_id: experimentId,
      variant_id: variantId,
      session_id: getSessionId(),
    })
  } catch {}
}

export function _resetForTests() {
  _config = null
  _subjectId = ''
  _exposed = new Set()
}
