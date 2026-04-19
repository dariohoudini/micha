import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const MOCK_NOTIFICATIONS = [
  { id: '1', type: 'order', title: 'Pedido confirmado', body: 'O seu pedido ORD-ABC123 foi confirmado.', time: '2 min', read: false },
  { id: '2', type: 'promo', title: 'Oferta especial', body: 'Flash sale! 30% de desconto em tecnologia hoje.', time: '1h', read: false },
  { id: '3', type: 'system', title: 'Bem-vindo ao MICHA Express', body: 'A sua conta foi verificada com sucesso. Comece a comprar!', time: '2h', read: true },
]

const TYPE_ICONS = {
  order:  { icon: 'M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z', color: '#C9A84C' },
  promo:  { icon: 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z', color: '#f59e0b' },
  system: { icon: 'M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0', color: '#3b82f6' },
}

export default function NotificationsPage() {
  const navigate = useNavigate()
  const [notifications, setNotifications] = useState(MOCK_NOTIFICATIONS)

  const markAllRead = () => setNotifications(n => n.map(notif => ({ ...notif, read: true })))
  const unread = notifications.filter(n => !n.read).length

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <div style={{ padding: '52px 16px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 12H5M12 5l-7 7 7 7" />
              </svg>
            </button>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Notificações</h1>
            {unread > 0 && (
              <span style={{ background: '#C9A84C', color: '#0A0A0A', fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20 }}>{unread}</span>
            )}
          </div>
          {unread > 0 && (
            <button onClick={markAllRead} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C', background: 'none', border: 'none', cursor: 'pointer' }}>
              Marcar todas
            </button>
          )}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {notifications.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60%', gap: 12, padding: '0 32px' }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center' }}>Sem notificações por enquanto</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', padding: '0 16px 20px' }}>
            {notifications.map((notif, i) => {
              const config = TYPE_ICONS[notif.type] || TYPE_ICONS.system
              return (
                <button
                  key={notif.id}
                  onClick={() => setNotifications(n => n.map(item => item.id === notif.id ? { ...item, read: true } : item))}
                  style={{
                    display: 'flex', gap: 14, alignItems: 'flex-start',
                    padding: '16px 0', textAlign: 'left',
                    background: 'none', border: 'none', cursor: 'pointer',
                    borderBottom: i < notifications.length - 1 ? '1px solid #141414' : 'none',
                  }}>
                  <div style={{
                    width: 42, height: 42, borderRadius: 12, flexShrink: 0,
                    background: `${config.color}15`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    position: 'relative',
                  }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={config.color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d={config.icon} />
                    </svg>
                    {!notif.read && (
                      <div style={{ position: 'absolute', top: -2, right: -2, width: 8, height: 8, borderRadius: '50%', background: '#C9A84C', border: '1.5px solid #0A0A0A' }} />
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: notif.read ? 400 : 600, color: '#FFFFFF', lineHeight: 1.3 }}>{notif.title}</p>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', flexShrink: 0 }}>{notif.time}</span>
                    </div>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginTop: 4, lineHeight: 1.4 }}>{notif.body}</p>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
