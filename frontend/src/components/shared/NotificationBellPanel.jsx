import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'
import { track } from '@/lib/userTrack'

/**
 * NotificationBellPanel — AliExpress Complete 2025 CH 1.3.
 *
 * The header bell icon opens an overlay panel listing the buyer's
 * most recent 8 notifications. Tapping a row marks-read and
 * navigates to its deep link. Tapping the [Ver tudo] footer goes
 * to the dedicated /notifications page. Tapping outside dismisses.
 *
 * Mount near the header: <NotificationBell /> renders the icon
 * with an unread-count badge AND owns the dropdown overlay.
 * Polls /api/v1/notifications/unread-count/ every 60s so the badge
 * stays roughly fresh; on open it does a one-shot list fetch.
 */

const S = { fontFamily: "'DM Sans', sans-serif" }

export default function NotificationBell() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [count, setCount] = useState(0)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const ref = useRef()

  // Poll unread count.
  useEffect(() => {
    const fetchCount = () => client.get('/api/v1/notifications/unread-count/')
      .then(r => setCount(r.data?.count || 0)).catch(() => {})
    fetchCount()
    const t = setInterval(fetchCount, 60_000)
    return () => clearInterval(t)
  }, [])

  // Click-outside to close.
  useEffect(() => {
    if (!open) return
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('touchstart', onClick)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('touchstart', onClick)
    }
  }, [open])

  const openPanel = async () => {
    setOpen(o => !o)
    if (open) return
    track('header.bell_opened', { unread: count })
    setLoading(true)
    try {
      const res = await client.get('/api/v1/notifications/?limit=8')
      setItems(res.data?.results || res.data || [])
    } catch { setItems([]) }
    finally { setLoading(false) }
  }

  const onRow = async (n) => {
    track('header.notification_tap', { id: n.id, kind: n.kind })
    try { await client.patch(`/api/v1/notifications/${n.id}/read/`) } catch {}
    setCount(c => Math.max(0, c - 1))
    setOpen(false)
    if (n.deep_link) navigate(n.deep_link)
    else navigate('/notifications')
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button onClick={openPanel}
        aria-label="Notificações"
        style={{ position: 'relative', width: 38, height: 38, borderRadius: 10, background: '#1E1E1E', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {count > 0 && (
          <span style={{ position: 'absolute', top: -3, right: -3, minWidth: 18, height: 18, padding: '0 5px', borderRadius: 9, background: '#ef4444', color: '#FFF', ...S, fontSize: 10, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {count > 9 ? '9+' : count}
          </span>
        )}
      </button>

      {open && (
        <div style={{ position: 'absolute', top: 46, right: 0, width: 320, maxHeight: 460, background: '#141414', border: '1px solid #2A2A2A', borderRadius: 14, boxShadow: '0 12px 32px rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #1E1E1E', display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ ...S, fontSize: 13, color: '#FFF', fontWeight: 700 }}>Notificações</span>
            <button onClick={async () => {
              try { await client.post('/api/v1/notifications/read-all/'); setCount(0); setItems(prev => prev.map(n => ({ ...n, is_read: true }))); track('header.mark_all_read', {}) } catch {}
            }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', ...S, fontSize: 11, color: '#C9A84C' }}>
              Marcar lidas
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {loading ? (
              <p style={{ ...S, fontSize: 12, color: '#9A9A9A', padding: 18, textAlign: 'center' }}>A carregar…</p>
            ) : items.length === 0 ? (
              <p style={{ ...S, fontSize: 12, color: '#9A9A9A', padding: 24, textAlign: 'center' }}>Sem notificações ainda</p>
            ) : items.map(n => (
              <button key={n.id} onClick={() => onRow(n)}
                style={{ width: '100%', display: 'flex', gap: 10, padding: '10px 14px', background: n.is_read ? 'transparent' : 'rgba(201,168,76,0.05)', border: 'none', borderBottom: '1px solid #1E1E1E', cursor: 'pointer', textAlign: 'left' }}>
                {!n.is_read && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#C9A84C', flexShrink: 0, marginTop: 5 }} />}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ ...S, fontSize: 12, color: '#FFF', fontWeight: n.is_read ? 400 : 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.title || n.message}</p>
                  {n.body && <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 2, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{n.body}</p>}
                  <p style={{ ...S, fontSize: 10, color: '#555', marginTop: 3 }}>{n.created_at ? new Date(n.created_at).toLocaleString('pt-AO') : ''}</p>
                </div>
              </button>
            ))}
          </div>
          <button onClick={() => { setOpen(false); navigate('/notifications') }}
            style={{ padding: '12px 0', background: '#0F0F0F', border: 'none', borderTop: '1px solid #1E1E1E', ...S, fontSize: 12, color: '#C9A84C', fontWeight: 700, cursor: 'pointer' }}>
            Ver todas →
          </button>
        </div>
      )}
    </div>
  )
}
