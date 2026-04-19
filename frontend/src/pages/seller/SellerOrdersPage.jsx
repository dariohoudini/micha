import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import { formatPrice } from '@/components/buyer/mockData'

const STATUS_CONFIG = {
  pending:   { label: 'Pendente',    color: '#f59e0b', bg: 'rgba(245,158,11,0.1)',  nextLabel: 'Confirmar',        nextStatus: 'confirmed', nextColor: '#C9A84C' },
  confirmed: { label: 'Confirmado', color: '#3b82f6', bg: 'rgba(59,130,246,0.1)',  nextLabel: 'Marcar enviado',   nextStatus: 'shipped',   nextColor: '#8b5cf6' },
  shipped:   { label: 'Enviado',    color: '#8b5cf6', bg: 'rgba(139,92,246,0.1)',  nextLabel: 'Confirmar entrega', nextStatus: 'delivered', nextColor: '#059669' },
  delivered: { label: 'Entregue',   color: '#059669', bg: 'rgba(5,150,105,0.1)',   nextLabel: null,               nextStatus: null,        nextColor: null },
  cancelled: { label: 'Cancelado',  color: '#dc2626', bg: 'rgba(220,38,38,0.1)',   nextLabel: null,               nextStatus: null,        nextColor: null },
}

const INITIAL_ORDERS = [
  { id: 'ORD-001', buyer: 'João Silva', phone: '923456789', product: 'Vestido Capulana Premium', qty: 2, total: 17000, status: 'pending', date: '13 Abr 09:32', province: 'Luanda', address: 'Rua do Futungo, Belas', urgent: true },
  { id: 'ORD-002', buyer: 'Maria Santos', phone: '912345678', product: 'Colar de Missangas', qty: 1, total: 4500, status: 'confirmed', date: '12 Abr 14:15', province: 'Benguela', address: 'Av. Norton de Matos, 45', urgent: false },
  { id: 'ORD-003', buyer: 'Pedro Neto', phone: '934567890', product: 'Bolsa de Couro Genuíno', qty: 1, total: 28000, status: 'shipped', date: '11 Abr 10:00', province: 'Luanda', address: 'Talatona, Rua 5', urgent: false },
  { id: 'ORD-004', buyer: 'Ana Costa', phone: '945678901', product: 'Vestido Capulana Premium', qty: 1, total: 8500, status: 'delivered', date: '10 Abr 16:20', province: 'Huambo', address: 'Rua Principal, 12', urgent: false },
  { id: 'ORD-005', buyer: 'Carlos Silva', phone: '956789012', product: 'Colar de Missangas', qty: 3, total: 13500, status: 'cancelled', date: '09 Abr 11:05', province: 'Luanda', address: 'Maianga, Bloco 7', urgent: false },
]

export default function SellerOrdersPage() {
  const navigate = useNavigate()
  const [orders, setOrders] = useState(INITIAL_ORDERS)
  const [filter, setFilter] = useState('all')
  const [expanded, setExpanded] = useState(null)
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 2500)
  }

  const updateStatus = (id, newStatus) => {
    setOrders(prev => prev.map(o => o.id === id ? { ...o, status: newStatus } : o))
    const messages = { confirmed: 'Pedido confirmado!', shipped: 'Marcado como enviado!', delivered: 'Entrega confirmada!' }
    showToast(messages[newStatus] || 'Estado actualizado.')
    setExpanded(null)
  }

  const cancelOrder = (id) => {
    setOrders(prev => prev.map(o => o.id === id ? { ...o, status: 'cancelled' } : o))
    showToast('Pedido cancelado.', 'error')
    setExpanded(null)
  }

  const filtered = filter === 'all' ? orders : orders.filter(o => o.status === filter)

  const counts = Object.keys(STATUS_CONFIG).reduce((acc, key) => {
    acc[key] = orders.filter(o => o.status === key).length
    return acc
  }, {})

  const totalRevenue = orders.filter(o => o.status === 'delivered').reduce((a, o) => a + o.total, 0)
  const pendingRevenue = orders.filter(o => ['pending', 'confirmed', 'shipped'].includes(o.status)).reduce((a, o) => a + o.total, 0)

  return (
    <SellerLayout title="Pedidos">
      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#FFFFFF', padding: '10px 20px', borderRadius: 12, fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap' }}>
          {toast.msg}
        </div>
      )}

      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        {/* Revenue summary */}
        <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
          {[
            { label: 'Receita confirmada', value: formatPrice(totalRevenue), color: '#059669' },
            { label: 'Em processamento', value: formatPrice(pendingRevenue), color: '#f59e0b' },
          ].map(s => (
            <div key={s.label} style={{ flex: 1, background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: '12px 14px' }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: s.color }}>{s.value}</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>{s.label}</p>
            </div>
          ))}
        </div>

        {/* Filter tabs with counts */}
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', scrollbarWidth: 'none', paddingBottom: 12 }}>
          <button onClick={() => setFilter('all')}
            style={{ padding: '6px 14px', borderRadius: 50, flexShrink: 0, border: `1.5px solid ${filter === 'all' ? '#C9A84C' : '#2A2A2A'}`, background: filter === 'all' ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: filter === 'all' ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
            Todos ({orders.length})
          </button>
          {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
            <button key={key} onClick={() => setFilter(key)}
              style={{ padding: '6px 14px', borderRadius: 50, flexShrink: 0, border: `1.5px solid ${filter === key ? cfg.color : '#2A2A2A'}`, background: filter === key ? `${cfg.color}18` : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: filter === key ? cfg.color : '#9A9A9A', cursor: 'pointer', whiteSpace: 'nowrap' }}>
              {cfg.label} {counts[key] > 0 && `(${counts[key]})`}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {filtered.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '50%', gap: 12 }}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
            </svg>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A' }}>Sem pedidos neste estado.</p>
          </div>
        ) : (
          <div style={{ padding: '0 16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {filtered.map(order => {
              const cfg = STATUS_CONFIG[order.status]
              const isExpanded = expanded === order.id
              return (
                <div key={order.id} style={{ background: '#141414', borderRadius: 14, border: `1px solid ${order.urgent && order.status === 'pending' ? 'rgba(245,158,11,0.3)' : '#1E1E1E'}`, overflow: 'hidden' }}>
                  {/* Urgent bar */}
                  {order.urgent && order.status === 'pending' && <div style={{ height: 2, background: '#f59e0b' }} />}

                  <div style={{ padding: 14 }}>
                    {/* Header */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#C9A84C' }}>{order.id}</span>
                        {order.urgent && order.status === 'pending' && (
                          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, fontWeight: 600, color: '#f59e0b', background: 'rgba(245,158,11,0.1)', padding: '2px 6px', borderRadius: 10 }}>URGENTE</span>
                        )}
                      </div>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 600, color: cfg.color, background: cfg.bg, padding: '3px 10px', borderRadius: 20 }}>{cfg.label}</span>
                    </div>

                    {/* Product */}
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF', fontWeight: 500, marginBottom: 4 }}>{order.product} ×{order.qty}</p>

                    {/* Buyer + date */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>👤 {order.buyer}</span>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>📅 {order.date}</span>
                    </div>

                    {/* Total + expand toggle */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 16, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(order.total)}</span>
                      <button onClick={() => setExpanded(isExpanded ? null : order.id)}
                        style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>
                        {isExpanded ? 'Recolher' : 'Ver detalhes'}
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: isExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      </button>
                    </div>

                    {/* Expanded details */}
                    {isExpanded && (
                      <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid #1E1E1E', display: 'flex', flexDirection: 'column', gap: 10 }}>
                        {/* Delivery info */}
                        <div style={{ background: '#0F0F0F', borderRadius: 10, padding: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
                          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 4 }}>Detalhes de entrega</p>
                          <div style={{ display: 'flex', gap: 8 }}>
                            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', width: 60 }}>Comprador</span>
                            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#FFFFFF' }}>{order.buyer}</span>
                          </div>
                          <div style={{ display: 'flex', gap: 8 }}>
                            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', width: 60 }}>Telefone</span>
                            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C' }}>+244 {order.phone}</span>
                          </div>
                          <div style={{ display: 'flex', gap: 8 }}>
                            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', width: 60 }}>Endereço</span>
                            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#FFFFFF' }}>{order.address}, {order.province}</span>
                          </div>
                        </div>

                        {/* Action buttons */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                          {cfg.nextStatus && (
                            <button onClick={() => updateStatus(order.id, cfg.nextStatus)}
                              style={{ width: '100%', padding: '12px 0', borderRadius: 12, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
                              {cfg.nextLabel}
                            </button>
                          )}
                          {['pending', 'confirmed'].includes(order.status) && (
                            <button onClick={() => cancelOrder(order.id)}
                              style={{ width: '100%', padding: '12px 0', borderRadius: 12, border: '1px solid rgba(220,38,38,0.3)', background: 'rgba(220,38,38,0.08)', fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: '#dc2626', cursor: 'pointer' }}>
                              Cancelar pedido
                            </button>
                          )}
                          {order.status === 'delivered' && (
                            <div style={{ background: 'rgba(5,150,105,0.1)', border: '1px solid rgba(5,150,105,0.2)', borderRadius: 12, padding: '12px 16px', textAlign: 'center' }}>
                              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#059669', fontWeight: 500 }}>✓ Pedido concluído com sucesso</span>
                            </div>
                          )}
                          {order.status === 'cancelled' && (
                            <div style={{ background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.2)', borderRadius: 12, padding: '12px 16px', textAlign: 'center' }}>
                              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#dc2626', fontWeight: 500 }}>✗ Pedido cancelado</span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </SellerLayout>
  )
}
