/**
 * frontend/src/lib/deepLinks.js
 * ──────────────────────────────
 *
 * Deep-link router for native (Capacitor) builds.
 *
 * iOS Universal Links and Android App Links deliver an https:// URL
 * to the app via the Capacitor ``App`` plugin's ``appUrlOpen`` event.
 * Without a handler, the URL just opens the WebView at its baseURL
 * (e.g., the home page) — losing the deep-link context entirely.
 *
 * This module:
 *   • Subscribes to ``appUrlOpen``
 *   • Parses the URL and maps host paths to in-app routes
 *   • Calls react-router's ``navigate()`` so transitions feel native
 *   • Cleans up listeners on unmount
 *
 * Also supports custom-scheme URLs (``micha://product/123``) which
 * the OAuth redirect path uses, plus deferred deep links: if the
 * app was COLD-launched from a link, the URL arrives BEFORE
 * react-router is mounted. We stash the pending path and consume
 * it on first ``useDeepLinks()`` mount.
 *
 * What this does NOT handle
 * ──────────────────────────
 * The native-side declaration (Info.plist Associated Domains for iOS,
 * AndroidManifest intent-filters for Android) — that's done in Xcode
 * / Android Studio config, not in JS. Without those, ``appUrlOpen``
 * never fires. See apps/seo/well_known.py for the server-side half.
 */
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const isNative = () => {
  try {
    // Avoid eager-importing @capacitor/core in non-native context —
    // some test/SSR paths don't have it.
    const { Capacitor } = require('@capacitor/core')
    return Capacitor.isNativePlatform()
  } catch {
    return false
  }
}


let pendingPath = null


function urlToAppPath(url) {
  if (!url || typeof url !== 'string') return null

  // Custom scheme: micha://product/123 → /product/123
  // (used by some OAuth providers; standard https:// links also work)
  const customSchemeMatch = url.match(/^[a-zA-Z][a-zA-Z0-9+\-.]*:\/\/[^/]*(\/.*)?$/)
  if (customSchemeMatch) {
    try {
      const u = new URL(url)
      // Drop the origin; keep path + search + hash.
      return (u.pathname || '/') + (u.search || '') + (u.hash || '')
    } catch {
      // Fallback: regex-extracted path component.
      return customSchemeMatch[1] || '/'
    }
  }

  // Bare relative path (unlikely but defensive).
  if (url.startsWith('/')) return url

  return null
}


/**
 * React hook: subscribe the current navigator to ``appUrlOpen`` events.
 * Idempotent across re-renders — adds/removes the listener cleanly.
 */
export function useDeepLinks() {
  const navigate = useNavigate()

  useEffect(() => {
    if (!isNative()) return

    // Drain any pending path captured BEFORE react-router was mounted.
    if (pendingPath) {
      const p = pendingPath
      pendingPath = null
      // Microtask-defer so navigate() runs after current effect chain
      // has committed.
      queueMicrotask(() => {
        try { navigate(p) } catch {}
      })
    }

    let removeListener = () => {}
    let cancelled = false

    import('@capacitor/app').then(({ App }) => {
      if (cancelled) return
      const sub = App.addListener('appUrlOpen', (event) => {
        const path = urlToAppPath(event?.url)
        if (!path) return
        try {
          navigate(path)
        } catch (e) {
          // Router not ready yet → stash for the next mount.
          pendingPath = path
        }
      })
      // Capacitor returns a Promise<{ remove }>; await indirectly.
      removeListener = async () => {
        try { (await sub).remove() } catch {}
      }
    }).catch(() => {})

    return () => {
      cancelled = true
      removeListener()
    }
  }, [navigate])
}


// Exposed for direct (non-hook) use from index.html bootstrap scripts
// if needed. The hook is the primary entry point.
export function captureColdLaunchPath(url) {
  const path = urlToAppPath(url)
  if (path) pendingPath = path
}
