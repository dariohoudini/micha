import { useEffect, useState } from 'react'
import { useUIStore } from '@/stores/uiStore'

/**
 * OfflineBanner — AliExpress Complete 2025 CH 26.1.
 *
 * Replaces the previous one-liner. Now shows:
 *   • Persistent banner when offline (was already there).
 *   • A transient "Reconectado ✓" toast for 2.5s when we go back
 *     online — gives the user explicit feedback the connection
 *     came back rather than just silently hiding the banner.
 *   • A [Retry] button on the banner that fires a synthetic
 *     `online` ping via fetch('/') so the user can force a check
 *     without waiting for the OS event.
 */

export default function OfflineBanner() {
  const isOnline = useUIStore(s => s.isOnline)
  const setOnline = useUIStore(s => s.setOnline)
  const [justBack, setJustBack] = useState(false)
  const [retrying, setRetrying] = useState(false)

  // When transitioning offline → online, flash a confirmation.
  useEffect(() => {
    if (isOnline === false) return
    let mounted = true
    const t = setTimeout(() => mounted && setJustBack(false), 2500)
    return () => { mounted = false; clearTimeout(t) }
  }, [isOnline])

  const ping = async () => {
    setRetrying(true)
    try {
      // Ping with no-cache so we don't get a stale 200 from SW.
      const res = await fetch('/api/v1/analytics/config/', { cache: 'no-store' })
      if (res.ok) {
        setOnline(true)
        setJustBack(true)
      }
    } catch {}
    finally { setRetrying(false) }
  }

  if (isOnline && justBack) {
    return (
      <div className="offline-banner" role="status" aria-live="polite"
        style={{ background: '#10b981', color: '#FFFFFF' }}>
        ✓ Reconectado
      </div>
    )
  }
  if (isOnline) return null

  return (
    <div className="offline-banner" role="alert" aria-live="assertive" aria-atomic="true">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <line x1="1" y1="1" x2="23" y2="23" />
        <path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55M5 12.55a10.94 10.94 0 0 1 5.17-2.39M10.71 5.05A16 16 0 0 1 22.56 9M1.42 9a15.91 15.91 0 0 1 4.7-2.88M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01" />
      </svg>
      <span style={{ flex: 1 }}>Sem ligação à internet</span>
      <button onClick={ping} disabled={retrying}
        style={{ background: 'rgba(0,0,0,0.25)', border: 'none', borderRadius: 8, padding: '4px 10px', color: '#FFFFFF', fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 700, cursor: retrying ? 'wait' : 'pointer' }}>
        {retrying ? '…' : 'Repetir'}
      </button>
    </div>
  )
}
