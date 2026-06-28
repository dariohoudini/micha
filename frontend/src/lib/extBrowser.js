/**
 * extBrowser — §1.3 In-App Browser
 *
 * Anything that is NOT a micha.ao / capacitor-localhost URL should
 * open in SafariViewController (iOS) / Chrome Custom Tabs (Android).
 * This is the AliExpress §1.3 behaviour: T&C, carrier tracking,
 * PayPal OAuth, social-share targets — all open in an in-app
 * browser that has a close button returning the user to the screen
 * they left from. We avoid leaving the app via `Linking.openURL`
 * because that drops session continuity and confuses iOS analytics.
 *
 * On web, falls back to `window.open(url, '_blank', noopener)`.
 *
 * Telemetry: every external open writes `external_url.open` to
 * UserEvent so we can see which T&C / docs / tracking pages users
 * actually tap on.
 */
import { Capacitor } from '@capacitor/core'
import { track } from '@/lib/userTrack'

// Domains that are part of MICHA itself — never bounced to an in-app
// browser, always handled by the SPA router. Keep this list tight
// and explicit; "*.micha.ao" wildcards are intentionally avoided so
// a misconfigured subdomain redirect can't bypass the gate.
const INTERNAL_HOSTS = new Set([
  'micha.ao', 'www.micha.ao', 'app.micha.ao',
  'localhost', '127.0.0.1',
])

export function isExternal(url) {
  try {
    const u = new URL(url, window.location.origin)
    if (u.protocol === 'capacitor:' || u.protocol === 'file:') return false
    return !INTERNAL_HOSTS.has(u.hostname)
  } catch {
    return false
  }
}

/**
 * Opens `url` in the in-app browser if external, otherwise lets the
 * caller handle it (returns false so they fall back to router).
 *
 * @param {string} url
 * @param {object} [opts]
 * @param {string} [opts.source] — tag for analytics, e.g. "pdp_share"
 */
export async function openExternal(url, opts = {}) {
  if (!url) return false
  try {
    track('external_url.open', {
      url: url.slice(0, 255),
      source: opts.source || 'unknown',
      native: Capacitor.isNativePlatform(),
    })
  } catch {}

  if (Capacitor.isNativePlatform()) {
    // Try Capacitor Browser plugin — installed lazily so the bundle
    // stays slim on web. The dynamic import keeps Vite from yelling
    // when the plugin isn't installed.
    try {
      const mod = await import('@capacitor/browser').catch(() => null)
      if (mod && mod.Browser && mod.Browser.open) {
        await mod.Browser.open({ url, presentationStyle: 'popover' })
        return true
      }
    } catch {}
  }

  // Web / fallback: open in a new tab with no opener so the target
  // site can't `window.opener.location = phishingURL` against us.
  try {
    window.open(url, '_blank', 'noopener,noreferrer')
    return true
  } catch {
    window.location.href = url
    return true
  }
}

/**
 * Drop-in onClick handler for <a href> targets. Lets cmd-click /
 * middle-click work on web, but routes a plain left-click through
 * the in-app browser path on native.
 *
 *   <a href={url} onClick={extLinkHandler(url, 'pdp_terms')}>T&C</a>
 */
export function extLinkHandler(url, source) {
  return (e) => {
    if (e && (e.metaKey || e.ctrlKey || e.button === 1)) return // let browser handle
    e?.preventDefault?.()
    openExternal(url, { source })
  }
}
