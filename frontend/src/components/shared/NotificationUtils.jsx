import api from '@/api/client'
export function groupNotifications(notifications) {
  const groups = {}
  notifications.forEach(n => {
    const type = n.notification_type || 'general'
    if (!groups[type]) groups[type] = { type, items: [], label: typeLabel(type) }
    groups[type].items.push(n)
  })
  return Object.values(groups)
}

function typeLabel(type) {
  const labels = {
    order_update: 'Actualizações de pedido',
    cart_abandonment: 'Carrinho',
    price_drop: 'Descidas de preço',
    promotion: 'Promoções',
    chat: 'Mensagens',
    general: 'Geral',
  }
  return labels[type] || 'Notificações'
}

export async function markAllNotificationsRead() {
  try {
    await api.post('/api/v1/notifications/read-all/')
  } catch {}
}

export function MarkAllReadButton({ onMarkAll }) {
  const handleClick = async () => {
    await markAllNotificationsRead()
    onMarkAll?.()
  }
  return (
    <button onClick={handleClick} style={{
      background: 'none', border: 'none', cursor: 'pointer',
      fontFamily: "'DM Sans', sans-serif", fontSize: 12,
      color: '#C9A84C', padding: '4px 0',
    }}>
      Marcar todas como lidas
    </button>
  )
}
