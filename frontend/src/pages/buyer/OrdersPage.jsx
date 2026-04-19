import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import client from '@/api/client'

const STATUS_CONFIG = {
  pending:   { label: 'Pendente',    color: '#f59e0b', bg: 'rgba(245,158,11,0.1)',  icon: '⏳' },
  confirmed: { label: 'Confirmado', color: '#3b82f6', bg: 'rgba(59,130,246,0.1)',  icon: '✓' },
  shipped:   { label: 'Enviado',    color: '#8b5cf6', bg: 'rgba(139,92,246,0.1)',  icon: '🚚' },
  delivered: { label: 'Entregue',   color: '#059669', bg: 'rgba(5,150,105,0.1)',   icon: '✅' },
  cancelled: { label: 'Cancelado',  color: '#dc2626', bg: 'rgba(220,38,38,0.1)',   icon: '✗' },
  dispute:   { label: 'Disputa',    color: '#f59e0b', bg: 'rgba(245,158,11,0.1)',  icon: '⚠️' },
}

const TRACKING_STEPS = [
  { status: 'pending',   label: 'Pedido recebido' },
  { status: 'confirmed', label: 'Confirmado pelo vendedor' },
  { status: 'shipped',   label: 'Em trânsito' },
  { status: 'delivered', label: 'Entregue' },
]

function TrackingTimeline({ currentStatus }) {
  const stepIndex = TRACKING_STEPS.findIndex(s => s.status === currentStatus)
  if (currentStatus === 'cancelled') return (
    <div style={{ background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.2)', borderRadius: 10, padding: '10px 14px', textAlign: 'center' }}>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#dc2626' }}>✗ Pedido cancelado</span>
    </div>
  )

  return (
    <div style={{ padding: '12px 0' }}>
      {TRACKING_STEPS.map((step, i) => {
        const done = i <= stepIndex
        const active = i === stepIndex
        return (
          <div key={step.status} style={{ display: 'flex', gap: 12, marginBottom: i < TRACKING_STEPS.length - 1 ? 0 : 0 }}>
            {/* Line + dot */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 20 }}>
              <div style={{ width: 18, height: 18, borderRadius: '50%', border: `2px solid ${done ? '#C9A84C' : '#2A2A2A'}`, background: done ? '#C9A84C' : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'all 0.3s' }}>
                {done && <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>}
              </div>
              {i < TRACKING_STEPS.length - 1 && (
                <div style={{ width: 2, height: 28, background: done ? '#C9A84C' : '#2A2A2A', transition: 'background 0.3s', margin: '2px 0' }} />
              )}
            </div>
            {/* Label */}
            <div style={{ paddingBottom: i < TRACKING_STEPS.length - 1 ? 20 : 0 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: active ? 600 : 400, color: done ? '#FFFFFF' : '#9A9A9A', transition: 'color 0.3s' }}>
                {step.label}
              </p>
              {active && (
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#C9A84C', marginTop: 2 }}>Em curso</p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function OrdersPage() {
  const navigate = useNavigate()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    loadOrders()
  }, [])

  const loadOrders = async () => {
    try {
      const res = await client.get('/api/orders/')
      setOrders(res.data.results || res.data || [])
    } catch (err) {
      console.error('Orders load failed:', err)
      setOrders([])
    } finally {
      setLoading(false)
    }
  }

  const filtered = filter === 'all' ? orders : orders.filter(o => o.status === filter)

  return (
    <BuyerLayout>
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
          </button>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>Os meus pedidos</h1>
        </div>

        {/* Filter tabs */}
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', scrollbarWidth: 'none', paddingBottom: 12 }}>
          {[
            { v: 'all', l: 'Todos' },
            { v: 'pending', l: 'Pendentes' },
            { v: 'shipped', l: 'Em trânsito' },
            { v: 'delivered', l: 'Entregues' },
            { v: 'cancelled', l: 'Cancelados' },
          ].map(tab => (
            <button key={tab.v} onClick={() => setFilter(tab.v)}
              style={{ padding: '6px 14px', borderRadius: 50, flexShrink: 0, border: `1.5px solid ${filter === tab.v ? '#C9A84C' : '#2A2A2A'}`, background: filter === tab.v ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: filter === tab.v ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
              {tab.l}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
            <div style={{ width: 24, height: 24, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }}>
              <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '50%', gap: 16, padding: '0 32px' }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
            </svg>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center' }}>
              {filter === 'all' ? 'Ainda não fez nenhum pedido.' : `Sem pedidos ${filter === 'delivered' ? 'entregues' : filter === 'cancelled' ? 'cancelados' : 'neste estado'}.`}
            </p>
            <button className="btn-primary" onClick={() => navigate('/explore')} style={{ width: 'auto', padding: '10px 24px' }}>
              Começar a comprar
            </button>
          </div>
        ) : (
          <div style={{ padding: '0 16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {filtered.map(order => {
              const status = STATUS_CONFIG[order.status] || STATUS_CONFIG.pending
              const isExpanded = expanded === (order.id || order.order_id)
              const orderId = order.id || order.order_id

              return (
                <div key={orderId} style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', overflow: 'hidden' }}>
                  {/* Order header */}
                  <div style={{ padding: 16 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#C9A84C' }}>
                        #{String(orderId).slice(-8).toUpperCase()}
                      </span>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 600, color: status.color, background: status.bg, padding: '3px 10px', borderRadius: 20 }}>
                        {status.icon} {status.label}
                      </span>
                    </div>

                    {/* Product(s) */}
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF', fontWeight: 500, marginBottom: 6 }}>
                      {order.product_name || order.items?.[0]?.product_name || 'Produto'}
                      {(order.items?.length > 1) && ` + ${order.items.length - 1} mais`}
                    </p>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 700, color: '#C9A84C' }}>
                        {Number(order.total || order.total_amount || 0).toLocaleString()} Kz
                      </span>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>
                        {order.created_at ? new Date(order.created_at).toLocaleDateString('pt-AO') : ''}
                      </span>
                    </div>

                    {/* Tracking timeline — shown when expanded */}
                    {isExpanded && (
                      <div style={{ borderTop: '1px solid #1E1E1E', paddingTop: 16, marginBottom: 8 }}>
                        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 12 }}>
                          Rastreamento
                        </p>
                        <TrackingTimeline currentStatus={order.status} />

                        {/* Delivery address */}
                        {order.delivery_address && (
                          <div style={{ background: '#0F0F0F', borderRadius: 10, padding: '10px 14px', marginTop: 12 }}>
                            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', marginBottom: 4 }}>Endereço de entrega</p>
                            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF' }}>{order.delivery_address}</p>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Actions */}
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => setExpanded(isExpanded ? null : orderId)}
                        style={{ flex: 1, padding: '9px 0', borderRadius: 10, border: '1px solid #2A2A2A', background: 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', cursor: 'pointer' }}>
                        {isExpanded ? 'Recolher' : 'Ver rastreamento'}
                      </button>
                      {order.status === 'delivered' && (
                        <button onClick={() => navigate(`/product/${order.product_id}`)}
                          style={{ flex: 1, padding: '9px 0', borderRadius: 10, border: '1px solid rgba(201,168,76,0.3)', background: 'rgba(201,168,76,0.08)', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C', cursor: 'pointer' }}>
                          Avaliar produto
                        </button>
                      )}
                      {order.status === 'pending' && (
                        <button style={{ flex: 1, padding: '9px 0', borderRadius: 10, border: '1px solid rgba(220,38,38,0.2)', background: 'rgba(220,38,38,0.06)', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#dc2626', cursor: 'pointer' }}>
                          Cancelar
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </BuyerLayout>
  )
}
