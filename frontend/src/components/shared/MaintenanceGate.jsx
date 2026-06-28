import { useEffect, useState } from 'react'
import { track } from '@/lib/userTrack'

/**
 * MaintenanceGate — AliExpress Complete 2025 CH 26.3.
 *
 * Polls /api/v1/analytics/config/ on mount and then every 60 seconds.
 * When the backend flips ``maintenance_mode=true`` we paint a
 * full-screen blocking overlay. When the buyer's app version is
 * below ``min_app_version`` we show an "Update required" modal
 * with a single CTA that opens the App Store / Play Store.
 *
 * Both responses come from the public AppConfigView so the gate
 * works even when the buyer is signed out.
 */

const S = { fontFamily: "'DM Sans', sans-serif" }

// Current app version baked in at build time. In a real release
// pipeline this comes from package.json / Capacitor config.
const APP_VERSION = (import.meta.env?.VITE_APP_VERSION || '1.0.0').toString()

function semverLt(a, b) {
  const pa = a.split('.').map(n => parseInt(n, 10) || 0)
  const pb = b.split('.').map(n => parseInt(n, 10) || 0)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = pa[i] || 0, y = pb[i] || 0
    if (x !== y) return x < y
  }
  return false
}

export default function MaintenanceGate() {
  const [cfg, setCfg] = useState(null)

  useEffect(() => {
    let cancelled = false
    const fetchCfg = async () => {
      try {
        const res = await fetch('/api/v1/analytics/config/', { credentials: 'include' })
        if (!res.ok) return
        const data = await res.json()
        if (!cancelled) {
          setCfg(data)
          if (data?.maintenance_mode) track('app.maintenance_active', {})
        }
      } catch {}
    }
    fetchCfg()
    const t = setInterval(fetchCfg, 60_000)
    return () => { cancelled = true; clearInterval(t) }
  }, [])

  if (!cfg) return null
  const needsUpdate = cfg.min_app_version && semverLt(APP_VERSION, cfg.min_app_version)
  const maint = !!cfg.maintenance_mode
  if (!needsUpdate && !maint) return null

  const openStore = () => {
    track('app.update_tap', { min: cfg.min_app_version, current: APP_VERSION })
    // iOS App Store / Play Store URLs would go here in production.
    // For now, surface a no-op that doesn't crash on web.
    if (typeof window !== 'undefined') {
      try {
        const ua = navigator.userAgent || ''
        if (/iPad|iPhone|iPod/i.test(ua)) {
          window.location.href = 'itms-apps://itunes.apple.com/app/micha-express/'
        } else if (/Android/i.test(ua)) {
          window.location.href = 'market://details?id=ao.micha.express'
        }
      } catch {}
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: '#0A0A0A', zIndex: 5000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ maxWidth: 360, width: '100%', textAlign: 'center' }}>
        <div style={{ fontSize: 60, marginBottom: 20 }}>{maint ? '🛠️' : '⬆️'}</div>
        <p style={{ ...S, fontSize: 20, fontWeight: 700, color: '#FFFFFF', marginBottom: 10 }}>
          {maint ? 'Estamos a melhorar o MICHA' : 'Actualização necessária'}
        </p>
        <p style={{ ...S, fontSize: 14, color: '#BFBFBF', lineHeight: 1.55, marginBottom: 20 }}>
          {maint
            ? (cfg.maintenance_message || 'Voltamos em breve.')
            : `A sua versão (${APP_VERSION}) já não é suportada. Por favor actualize para v${cfg.min_app_version}.`}
        </p>
        {!maint && (
          <button onClick={openStore}
            style={{ width: '100%', padding: '14px 0', borderRadius: 12, border: 'none', background: '#C9A84C', ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
            Actualizar agora
          </button>
        )}
        {maint && cfg.maintenance_until && (
          <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 14 }}>
            Previsto: {new Date(cfg.maintenance_until).toLocaleString('pt-AO')}
          </p>
        )}
      </div>
    </div>
  )
}
