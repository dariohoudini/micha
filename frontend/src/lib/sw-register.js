/**
 * Service Worker registration — Tier 7.
 *
 * Gated by VITE_ENABLE_SW (default 'true' in prod, 'false' in dev).
 * Wired from main.jsx on a slight delay so it never delays first paint.
 */

export function registerServiceWorker() {
  if (typeof window === 'undefined') return
  if (!('serviceWorker' in navigator)) return

  const enabled = import.meta.env?.VITE_ENABLE_SW
  if (enabled === 'false' || enabled === false) return
  if (import.meta.env?.DEV && enabled !== 'true' && enabled !== true) {
    // Default OFF in dev to avoid stale-asset confusion during HMR.
    return
  }

  // Register after first paint to keep TTI clean.
  const start = () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .catch(() => { /* silent — SW is opportunistic */ })
  }
  if (document.readyState === 'complete') start()
  else window.addEventListener('load', start, { once: true })
}
