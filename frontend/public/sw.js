/**
 * Service Worker — MICHA Tier 7.
 *
 * Strategy
 * ────────
 *  • Hashed Vite asset files (assets/*.<hash>.{js,css,woff2,svg,
 *    webp,avif,png,jpg}) — cache-first, 1 year. Vite emits hashed
 *    filenames so a deploy rotates the URL → no stale-asset risk.
 *  • index.html — network-first with fallback to cache. New deploys
 *    reach users immediately; offline users see last cached version.
 *  • API responses — NOT cached. Stale data risk on financial paths
 *    isn't worth the speed win.
 *
 * Registration is wired in main.jsx (R3 chapter).
 */

const STATIC_CACHE = 'micha-static-v1'
const SHELL_CACHE = 'micha-shell-v1'


self.addEventListener('install', (event) => {
  // Pre-cache the SPA shell so first-paint offline-from-cold works.
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(['/', '/index.html']))
      .catch(() => {})
  )
  self.skipWaiting()
})


self.addEventListener('activate', (event) => {
  // Drop old cache versions.
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names
          .filter((n) => n !== STATIC_CACHE && n !== SHELL_CACHE)
          .map((n) => caches.delete(n)),
      ),
    ),
  )
  self.clients.claim()
})


self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return
  const url = new URL(request.url)

  // Never touch the API.
  if (url.pathname.startsWith('/api/')) return

  // Hashed assets: cache-first.
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(cacheFirst(STATIC_CACHE, request))
    return
  }

  // SPA shell + everything else: network-first.
  event.respondWith(networkFirstShell(request))
})


async function cacheFirst(cacheName, request) {
  const cache = await caches.open(cacheName)
  const cached = await cache.match(request)
  if (cached) return cached
  try {
    const fresh = await fetch(request)
    if (fresh.ok) cache.put(request, fresh.clone())
    return fresh
  } catch (e) {
    if (cached) return cached
    return new Response('', { status: 504, statusText: 'offline' })
  }
}


async function networkFirstShell(request) {
  const cache = await caches.open(SHELL_CACHE)
  try {
    const fresh = await fetch(request)
    if (fresh.ok) cache.put(request, fresh.clone())
    return fresh
  } catch {
    const cached = await cache.match(request)
    if (cached) return cached
    // Last-resort: serve the SPA index so the router takes over.
    const indexCached = await cache.match('/index.html')
    if (indexCached) return indexCached
    return new Response('Offline', { status: 503, statusText: 'offline' })
  }
}
