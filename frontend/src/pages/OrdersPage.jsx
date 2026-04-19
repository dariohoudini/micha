import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import BottomNav from '@/components/shared/BottomNav'

const STATUS_CONFIG = {
  pending:    { label: 'Pendente',    color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
  confirmed:  { label: 'Confirmado', color: '#3b82f6', bg: 'rgba(59,130,246,0.1)' },
  shipped:    { label: 'Em trânsito', color: '#8b5cf6', bg: 'rgba(139,92,246,0.1)' },
  delivered:  { label: 'Entregue',   color: '#059669', bg: 'rgba(5,150,105,0.1)' },
  cancelled:  { label: 'Cancelado',  color: '#dc2626', bg: 'rgba(220,38,38,0.1)' },
}

// Mock orders — replace with ordersAPI.getOrders() when backend ready
const MOCK_ORDERS = []

export default function OrdersPage() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState('all')

  const filtered = filter === 'all' ? MOCK_ORDERS : MOCK_ORDERS.filter(o => o.status === filter)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <button onClick={() => navigate('/profile')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: '#FFFFFF' }}>Os meus pedidos</h1>
        </div>

        {/* Filter tabs */}
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', scrollbarWidth: 'none', paddingBottom: 16 }}>
          {[{ value: 'all', label: 'Todos' }, ...Object.entries(STATUS_CONFIG).map(([k, v]) => ({ value: k, label: v.label }))].map(tab => (
            <button key={tab.value} onClick={() => setFilter(tab.value)}
              style={{
                padding: '7px 14px', borderRadius: 50, flexShrink: 0,
                border: `1.5px solid ${filter === tab.value ? '#C9A84C' : '#2A2A2A'}`,
                background: filter === tab.value ? 'rgba(201,168,76,0.1)' : 'transparent',
                fontFamily: "'DM Sans', sans-serif", fontSize: 12,
                color: filter === tab.value ? '#C9A84C' : '#9A9A9A',
                cursor: 'pointer', whiteSpace: 'nowrap',
              }}>
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {filtered.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60%', gap: 16, padding: '0 32px' }}>
            <div style={{ width: 72, height: 72, borderRadius: 18, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2" />
              </svg>
            </div>
            <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF', textAlign: 'center' }}>Sem pedidos ainda</h2>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center' }}>Os seus pedidos aparecerão aqui após a primeira compra.</p>
            <button className="btn-primary" onClick={() => navigate('/home')} style={{ marginTop: 4 }}>Começar a comprar</button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '0 16px 20px' }}>
            {filtered.map(order => {
              const status = STATUS_CONFIG[order.status]
              return (
                <button key={order.id} onClick={() => navigate(`/orders/${order.id}`)}
                  style={{ display: 'flex', flexDirection: 'column', gap: 12, background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', padding: 16, cursor: 'pointer', textAlign: 'left' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#C9A84C' }}>{order.id}</span>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: status.color, background: status.bg, padding: '4px 10px', borderRadius: 20 }}>{status.label}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>{order.date} · {order.items} produto(s)</span>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700, color: '#FFFFFF' }}>{order.total}</span>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>
      <BottomNav />
    </div>
  )
}
