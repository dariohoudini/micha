/**
 * flags — feature flags + A/B testing client (Tier 9).
 *
 * Consumes the apps/flags backend:
 *   GET /api/v1/flags/?keys=foo,bar  → {flags: {foo: 'A', bar: true}}
 *
 * Sticky bucketing happens server-side (the backend hashes user_id
 * or session_id into the variant). This client just reads the
 * resolved values.
 *
 * Public API
 * ──────────
 *   await loadFlags(keys: string[]) → {key: variant}
 *   isOn(key) — boolean check
 *   variant(key) — A/B/C string
 *   useFlag(key) — React hook
 *   useFlags(keys[]) — React hook
 *   exposeFlag(key, variant) — emit exposure event for funnel analysis
 *
 * Stale-while-revalidate
 * ──────────────────────
 * Flag values are cached in memory for the session. First call
 * fetches; subsequent reads are synchronous. After 5 minutes, the
 * next read triggers a background refresh while returning the cached
 * value (no UI flicker).
 */
import { useEffect, useState } from 'react'
import client from '@/api/client'
import { track } from './events'


const STALE_MS = 5 * 60 * 1000


let _cache = {}
let _cacheStamp = 0
let _exposed = new Set()


export async function loadFlags(keys) {
  if (!Array.isArray(keys) || keys.length === 0) return {}
  try {
    const { data } = await client.get('/api/v1/flags/', {
      params: { keys: keys.join(',') },
    })
    const flags = data?.flags || data || {}
    _cache = { ..._cache, ...flags }
    _cacheStamp = Date.now()
    return flags
  } catch {
    return {}
  }
}


export function isOn(key) {
  const v = _cache[key]
  return v === true || v === 'on' || v === 'A'
}


export function variant(key, fallback = 'control') {
  const v = _cache[key]
  if (v === undefined || v === null) return fallback
  return String(v)
}


/**
 * Emit an "exposure" event so funnel analysis can correlate variant
 * to outcome. Idempotent — only fires once per (key, variant) pair
 * per session.
 */
export function exposeFlag(key, value) {
  const stamp = `${key}=${value}`
  if (_exposed.has(stamp)) return
  _exposed.add(stamp)
  track('flag_exposed', { flag: key, variant: String(value) })
}


/* ─── React hooks ────────────────────────────────────────────────── */

/**
 * Resolve a single flag.
 *
 *   const v = useFlag('checkout_redesign_v2', { fallback: 'control' })
 *   if (v === 'B') return <NewCheckout />
 *   return <OldCheckout />
 *
 * Auto-exposes on mount.
 */
export function useFlag(key, opts = {}) {
  const fallback = opts.fallback ?? 'control'
  const [val, setVal] = useState(() => {
    return _cache[key] !== undefined ? variant(key, fallback) : null
  })

  useEffect(() => {
    let cancelled = false

    // Cached + fresh — use it immediately.
    if (_cache[key] !== undefined && Date.now() - _cacheStamp < STALE_MS) {
      const v = variant(key, fallback)
      setVal(v)
      exposeFlag(key, v)
      return
    }

    loadFlags([key]).then(() => {
      if (cancelled) return
      const v = variant(key, fallback)
      setVal(v)
      exposeFlag(key, v)
    })

    return () => { cancelled = true }
  }, [key, fallback])

  return val ?? fallback
}


export function useFlags(keys) {
  const [resolved, setResolved] = useState({})

  useEffect(() => {
    let cancelled = false
    loadFlags(keys).then((flags) => {
      if (!cancelled) setResolved(flags)
    })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keys.join(',')])

  return resolved
}
