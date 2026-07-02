import { useState, useEffect } from 'react'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'
import HelperBot from '@/components/shared/HelperBot'
import SwipeToDelete from '@/components/shared/SwipeToDelete'
import { MarkAllReadButton, groupNotifications } from '@/components/shared/NotificationUtils'
import { asList } from '@/lib/asList'

const GOLD = '#C9A84C', CARD = '#1E1E1E', BORDER = '#2A2A2A', TEXT = '#FFFFFF', MUTED = '#9A9A9A', BG = '#0A0A0A'

const TYPE_ICONS = {
  order_update: '📦', price_drop: '📉', back_in_stock: '✅',
  promotion: '🎉', cart_abandonment: '🛒', chat: '💬', general: '🔔',
}

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadNotifications() }, [])

  const loadNotifications = async () => {
    setLoading(true)
    try {
      const res = await client.get('/api/v1/notifications/')
      setNotifications(asList(res.data))
    } catch {}
    setLoading(false)
  }

  const markAllRead = async () => {
    await client.patch('/api/v1/notifications/mark-all-read/').catch(() => {})
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
  }

  const dismiss = async (id) => {
    setNotifications(prev => prev.filter(n => n.id !== id))
    await client.patch(`/api/v1/notifications/${id}/read/`).catch(() => {})
  }

  const unread = notifications.filter(n => !n.is_read).length

  return (
    <BuyerLayout title="Notificações">
      <div style={{ flex: 1, overflowY: 'auto', background: BG }}>
        {/* Header */}
        <div style={{ padding: '16px 16px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: TEXT, margin: 0 }}>Notificações</h1>
            {unread > 0 && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: GOLD, margin: '2px 0 0' }}>{unread} não lida{unread > 1 ? 's' : ''}</p>}
          </div>
          {unread > 0 && <MarkAllReadButton onMarkAll={markAllRead} />}
        </div>

        {/* List */}
        <div style={{ padding: '0 16px 80px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {loading ? (
            [1,2,3].map(i => (
              <div key={i} style={{ background: CARD, borderRadius: 12, padding: 14, border: `1px solid ${BORDER}` }}>
                <div style={{ height: 12, background: BORDER, borderRadius: 4, width: '60%', marginBottom: 8, animation: 'pulse 1.5s infinite' }} />
                <div style={{ height: 10, background: BORDER, borderRadius: 4, width: '90%', animation: 'pulse 1.5s infinite' }} />
                <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>
              </div>
            ))
          ) : notifications.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '60px 0' }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🔔</div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: TEXT, margin: '0 0 6px' }}>Sem notificações</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: MUTED }}>Quando tiveres novidades aparecerão aqui</p>
            </div>
          ) : (
            notifications.map(n => (
              <SwipeToDelete key={n.id} onDelete={() => dismiss(n.id)} deleteLabel="Dispensar">
                <div style={{
                  background: n.is_read ? CARD : 'rgba(201,168,76,0.06)',
                  borderRadius: 12, padding: 14,
                  border: `1px solid ${n.is_read ? BORDER : 'rgba(201,168,76,0.2)'}`,
                  display: 'flex', gap: 12, alignItems: 'flex-start',
                }}>
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: BORDER, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>
                    {TYPE_ICONS[n.notification_type] || '🔔'}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: n.is_read ? 400 : 600, color: TEXT, margin: '0 0 3px' }}>{n.title}</p>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: MUTED, margin: '0 0 4px', lineHeight: 1.5 }}>{n.message}</p>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: MUTED, margin: 0 }}>
                      {new Date(n.created_at).toLocaleDateString('pt-AO', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </div>
                  {!n.is_read && <div style={{ width: 8, height: 8, borderRadius: '50%', background: GOLD, flexShrink: 0, marginTop: 4 }} />}
                </div>
              </SwipeToDelete>
            ))
          )}
        </div>
      </div>
      <HelperBot screen="orders" isSeller={false} />
    </BuyerLayout>
  )
}
