#!/usr/bin/env node
/**
 * frontend/scripts/check-bundle-size.mjs
 *
 * Post-build bundle size budget enforcement (R5 / R1 Sprint 3).
 *
 * Reads dist/assets/*.js, compares each chunk against the budget
 * table below, and exits non-zero if any chunk exceeds. Wire into
 * CI right after `npm run build` to fail the build on regressions.
 *
 * Why a budget enforcer
 * ─────────────────────
 * Bundle sizes creep — a 20KB dependency added today, a 50KB
 * polyfill next month, a year later the main bundle is 700KB and
 * mobile users on Angolan 4G wait 8 seconds to interact. Catching
 * each regression at PR time is the only way to keep size honest.
 *
 * Budgets are GZIPPED sizes — that's what users actually download.
 *
 * Run: node scripts/check-bundle-size.mjs
 */

import { readdir, stat, readFile } from 'node:fs/promises'
import { gzipSync } from 'node:zlib'
import { join } from 'node:path'

const ASSETS_DIR = new URL('../dist/assets/', import.meta.url).pathname

// Per-chunk gzipped budget in KB. New entries default to 100KB if
// not listed — adjust upward only after deliberate review.
//
// Why these numbers
// ─────────────────
// Mobile 4G median throughput in Luanda ~ 1 MB/s. Each 100KB chunk
// adds ~100ms of network time. The hot path on first paint should
// fit under 250KB gzipped; route chunks under 50KB.
const BUDGETS_KB = {
  'index':           90,    // app shell + router boot
  'vendor-react':    80,    // React 19 + react-dom + router
  'vendor-axios':    20,
  'vendor-forms':    35,    // hook-form + zod + @hookform
  'vendor-i18n':     20,
  'vendor-motion':   45,    // framer-motion is heavy but lazy
  'vendor-query':    15,    // tanstack
  'vendor-zustand':  5,
  'AreaChart':       110,   // recharts — load only on admin pages
  'SellerAnalyticsPage': 25,
  // Default for unknown chunks:
  '__default':       55,
}

function budgetFor(name) {
  for (const [prefix, kb] of Object.entries(BUDGETS_KB)) {
    if (prefix === '__default') continue
    if (name.startsWith(prefix)) return kb
  }
  return BUDGETS_KB.__default
}

async function main() {
  let files
  try {
    files = await readdir(ASSETS_DIR)
  } catch {
    console.error(`[bundle-budget] dist/assets/ not found — run \`npm run build\` first.`)
    process.exit(2)
  }

  const js = files.filter(f => f.endsWith('.js'))
  const violations = []
  let totalGzipKb = 0

  for (const f of js) {
    const path = join(ASSETS_DIR, f)
    const raw = await readFile(path)
    const gzip = gzipSync(raw)
    const gzipKb = +(gzip.length / 1024).toFixed(2)
    totalGzipKb += gzipKb

    // Strip hash suffix to match against BUDGETS_KB prefix.
    const base = f.replace(/-[a-zA-Z0-9_-]+\.js$/, '')
    const budget = budgetFor(base)
    const ratio = gzipKb / budget

    const flag = ratio > 1 ? 'FAIL' : ratio > 0.85 ? 'WARN' : '    '
    console.log(
      `${flag} ${base.padEnd(35)} ${gzipKb.toFixed(2).padStart(7)} KB ` +
      `(budget ${budget} KB, ${(ratio * 100).toFixed(0)}%)`
    )

    if (gzipKb > budget) {
      violations.push({ base, gzipKb, budget })
    }
  }

  console.log()
  console.log(`Total JS gzipped: ${totalGzipKb.toFixed(2)} KB across ${js.length} chunks`)

  if (violations.length) {
    console.error()
    console.error(`[bundle-budget] ${violations.length} chunk(s) over budget:`)
    for (const v of violations) {
      console.error(`  - ${v.base}: ${v.gzipKb} KB > ${v.budget} KB`)
    }
    console.error()
    console.error('Either add a lazy boundary or, with deliberate review,')
    console.error('bump the budget in scripts/check-bundle-size.mjs.')
    process.exit(1)
  }

  console.log('[bundle-budget] all chunks within budget ✓')
}

main().catch((e) => {
  console.error('[bundle-budget] crashed:', e)
  process.exit(2)
})
