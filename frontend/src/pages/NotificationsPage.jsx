import { useNavigate } from 'react-router-dom'
import { useNotifications, useMarkNotificationRead, useMarkAllRead } from '@/hooks/useQueries'
import PageHeader from '@/components/ui/PageHeader'
import Badge from '@/components/ui/Badge'
import EmptyState from '@/components/ui/EmptyState'
import Button from '@/components/ui/Button'

const TYPE_CONFIG = {
  order:   { icon: 'M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z', color: '#C9A84C' },
  promo:   { icon: 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z', color: '#f59e0b' },
  system:  { icon: 'M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0', color: '#3b82f6' },
  payment: { icon: 'M21 12V7H5a2 2 0 0 1 0-4h14v4M3 5v14a2 2 0 0 0 2 2h16v-5', color: '#059669' },
  review:  { icon: 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z', color: '#8b5cf6' },
}

function formatRelativeTime(dateStr) {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr)) / 1000)
  if (diff < 60) return 'Agora'
  if (diff < 3600) return `${Math.floor(diff / 60)} min`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`
  if (diff < 604800) return `${Math.floor(diff / 86400)}d`
  return new Date(dateStr).toLocaleDateString('pt-AO', { day: '2-digit', month: 'short' })
}

function NotificationRow({ notification, onMarkRead }) {
  const cfg = TYPE_CONFIG[notification.type] || TYPE_CONFIG.system
  const isUnread = !notification.is_read

  return (
    <button
      onClick={() => isUnread && onMarkRead(notification.id)}
      aria-label={`${notification.title}${isUnread ? ' (não lida)' : ''}`}
      style={{
        display: 'flex', gap: 14, alignItems: 'flex-start',
        padding: '16px 0', textAlign: 'left', width: '100%',
        background: 'none', border: 'none', cursor: isUnread ? 'pointer' : 'default',
      }}
    >
      <div style={{
        width: 44, height: 44, borderRadius: 13, flexShrink: 0,
        background: `${cfg.color}15`, border: `1px solid ${cfg.color}25`,
        display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative',
      }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={cfg.color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d={cfg.icon} />
        </svg>
        {isUnread && (
          <span aria-hidden="true" style={{
            position: 'absolute', top: -3, right: -3,
            width: 9, height: 9, borderRadius: '50%',
            background: '#C9A84C', border: '1.5px solid #0A0A0A',
          }} />
        )}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 3 }}>
          <p style={{
            fontFamily: "'DM Sans', sans-serif", fontSize: 14,
            fontWeight: isUnread ? 700 : 500,
            color: isUnread ? '#FFFFFF' : '#C8C8C8', lineHeight: 1.3,
          }}>
            {notification.title}
          </p>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#555', flexShrink: 0 }}>
            {formatRelativeTime(notification.created_at)}
          </span>
        </div>
        <p style={{
          fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', lineHeight: 1.4,
          overflow: 'hidden', display: '-webkit-box',
          WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
        }}>
          {notification.message}
        </p>
      </div>
    </button>
  )
}

export default function NotificationsPage() {
  const navigate = useNavigate()
  const { data: notifications = [], isLoading } = useNotifications()
  const markRead = useMarkNotificationRead()
  const markAllRead = useMarkAllRead()
  const unread = notifications.filter(n => !n.is_read).length

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <div aria-live="polite" aria-atomic="true" className="sr-only" id="notif-live-region" />

      <PageHeader
        title="Notificações"
        badge={unread > 0 ? <Badge variant="gold">{unread}</Badge> : null}
        right={
          unread > 0 ? (
            <button
              onClick={() => markAllRead.mutate()}
              disabled={markAllRead.isPending}
              style={{
                fontFamily: "'DM Sans', sans-serif", fontSize: 12,
                fontWeight: 600, color: '#C9A84C',
                background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0',
              }}
            >
              Marcar todas
            </button>
          ) : null
        }
      />

      <div className="screen" role="main" aria-label="Lista de notificações" style={{ flex: 1 }}>
        {isLoading ? (
          <div style={{ padding: '0 16px' }}>
            {[...Array(5)].map((_, i) => (
              <div key={i} style={{ display: 'flex', gap: 14, padding: '16px 0', borderBottom: '1px solid #141414' }}>
                <div className="skeleton" style={{ width: 44, height: 44, borderRadius: 13, flexShrink: 0 }} />
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 3 }}>
                  <div className="skeleton" style={{ height: 14, width: '55%', borderRadius: 6 }} />
                  <div className="skeleton" style={{ height: 12, width: '80%', borderRadius: 6 }} />
                </div>
              </div>
            ))}
          </div>
        ) : notifications.length === 0 ? (
          <EmptyState
            icon={
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
            }
            title="Sem notificações"
            description="As suas notificações vão aparecer aqui quando houver novidades."
            action={<Button variant="gold_ghost" size="sm" onClick={() => navigate('/')}>Explorar produtos</Button>}
          />
        ) : (
          <div style={{ padding: '0 16px 20px' }} className="stagger">
            {notifications.map((n, i) => (
              <div key={n.id} style={{ borderBottom: i < notifications.length - 1 ? '1px solid #141414' : 'none' }}>
                <NotificationRow notification={n} onMarkRead={(id) => markRead.mutate(id)} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
