/**
 * CartSyncIndicator — small status pill consuming cartStore.syncStatus.
 *
 * Variants
 * ────────
 *   idle     hidden (anonymous user, nothing to sync)
 *   syncing  spinning dot
 *   synced   green dot + "synced 2m ago" on hover/tap
 *   offline  orange dot + "offline — will sync when back"
 *   error    red dot + retry CTA
 *
 * Two modes
 * ─────────
 *   <CartSyncIndicator /> — inline, expanded with text + timestamp.
 *     Use on the cart page itself.
 *   <CartSyncIndicator dot /> — just the colored dot. Use as overlay
 *     on the cart icon in the bottom nav.
 */
import { useEffect, useState } from 'react'
import { useCartStore } from '@/stores/cartStore'


function timeAgo(ms) {
  if (!ms) return ''
  const diff = Math.max(0, Date.now() - ms)
  const secs = Math.floor(diff / 1000)
  if (secs < 5) return 'agora'
  if (secs < 60) return `${secs}s atrás`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m atrás`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h atrás`
  return `${Math.floor(hrs / 24)}d atrás`
}


const PALETTE = {
  idle:    { color: 'transparent',  label: '' },
  syncing: { color: '#FBBF24',      label: 'A sincronizar…' },
  synced:  { color: '#4ADE80',      label: 'Sincronizado' },
  offline: { color: '#FB923C',      label: 'Offline — sincroniza quando voltar a ligação' },
  error:   { color: '#F87171',      label: 'Falha na sincronização' },
}


export default function CartSyncIndicator({ dot = false }) {
  const status = useCartStore((s) => s.syncStatus)
  const lastSyncedAt = useCartStore((s) => s.lastSyncedAt)
  const [, force] = useState(0)

  // Re-tick the "X ago" label every 30s while mounted.
  useEffect(() => {
    if (status !== 'synced') return
    const id = setInterval(() => force((n) => n + 1), 30_000)
    return () => clearInterval(id)
  }, [status])

  if (status === 'idle') return null
  const p = PALETTE[status]

  if (dot) {
    return (
      <span
        aria-label={p.label}
        role="status"
        style={{
          display: 'inline-block',
          width: 8, height: 8, borderRadius: 999,
          background: p.color,
          animation: status === 'syncing' ? 'sync-pulse 1.2s ease-in-out infinite' : 'none',
          boxShadow: status === 'synced' ? '0 0 4px rgba(74, 222, 128, 0.6)' : 'none',
        }}
      >
        <style>{`
          @keyframes sync-pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
          }
        `}</style>
      </span>
    )
  }

  return (
    <div role="status" aria-live="polite" style={{
      display: 'inline-flex', alignItems: 'center', gap: 8,
      padding: '6px 10px', borderRadius: 999,
      background: 'rgba(13, 13, 26, 0.6)',
      border: `1px solid ${p.color}40`,
      fontSize: 12, color: '#E2E8F0',
    }}>
      <span aria-hidden style={{
        width: 8, height: 8, borderRadius: 999, background: p.color,
        animation: status === 'syncing' ? 'sync-pulse 1.2s ease-in-out infinite' : 'none',
      }} />
      <span>{p.label}</span>
      {status === 'synced' && lastSyncedAt && (
        <span style={{ color: '#94A3B8' }}>
          · {timeAgo(lastSyncedAt)}
        </span>
      )}
      <style>{`
        @keyframes sync-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  )
}
