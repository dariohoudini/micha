import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import { useAuthStore } from '@/stores/authStore'
import { formatPrice } from '@/components/buyer/mockData'

const INITIAL_ORDERS = [
  { id: 'ORD-001', buyer: 'João Silva', product: 'Vestido Capulana Premium', qty: 2, total: 17000, time: '5 min atrás', province: 'Luanda', urgent: true },
  { id: 'ORD-002', buyer: 'Maria Santos', product: 'Colar de Missangas', qty: 1, total: 4500, time: '23 min atrás', province: 'Benguela', urgent: false },
  { id: 'ORD-003', buyer: 'Pedro Neto', product: 'Bolsa de Couro Genuíno', qty: 1, total: 28000, time: '1h atrás', province: 'Luanda', urgent: false },
]

const ACTIVE_PRODUCTS = [
  { id: '1', name: 'Vestido Capulana Premium', price: 8500, stock: 24, sales: 34, views: 892, image_color: '#8B4513', status: 'active' },
  { id: '2', name: 'Colar de Missangas Tradicional', price: 4500, stock: 50, sales: 28, views: 654, image_color: '#1a1a2e', status: 'active' },
  { id: '3', name: 'Bolsa de Couro Genuíno', price: 28000, stock: 3, sales: 12, views: 421, image_color: '#5c3d2e', status: 'active' },
  { id: '4', name: 'Pulseira de Prata Angola', price: 6500, stock: 0, sales: 8, views: 234, image_color: '#2d3748', status: 'out_of_stock' },
]

export default function SellerDashboardPage() {
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)
  const [orders, setOrders] = useState(INITIAL_ORDERS)
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  const confirmOrder = (id) => {
    setOrders(prev => prev.filter(o => o.id !== id))
    showToast('Pedido confirmado! O comprador foi notificado.')
  }

  const rejectOrder = (id) => {
    setOrders(prev => prev.filter(o => o.id !== id))
    showToast('Pedido rejeitado.', 'error')
  }

  const ACTION_ITEMS = [
    { type: 'order', count: orders.length, label: 'Pedidos a confirmar', color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', path: '/seller/orders', icon: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2' },
    { type: 'shipped', count: 1, label: 'Envios pendentes', color: '#8b5cf6', bg: 'rgba(139,92,246,0.1)', path: '/seller/orders', icon: 'M5 12h14M12 5l7 7-7 7' },
    { type: 'stock', count: ACTIVE_PRODUCTS.filter(p => p.stock === 0).length, label: 'Stock esgotado', color: '#dc2626', bg: 'rgba(220,38,38,0.1)', path: '/seller/products', icon: 'M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78' },
    { type: 'analytics', count: null, label: 'Ver análises', color: '#C9A84C', bg: 'rgba(201,168,76,0.1)', path: '/seller/analytics', icon: 'M18 20V10M12 20V4M6 20v-6' },
  ]

  return (
    <SellerLayout title="Centro de Vendas">
      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)',
          zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669',
          color: '#FFFFFF', padding: '10px 20px', borderRadius: 12,
          fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500,
          boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap',
        }}>
          {toast.msg}
        </div>
      )}

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ paddingBottom: 24 }}>

          {/* Stats bar */}
          <div style={{ padding: '12px 16px 0' }}>
            <div style={{ display: 'flex', gap: 10 }}>
              {[
                { label: 'Hoje', value: '53 500 Kz', sub: 'receita', color: '#C9A84C', path: '/seller/analytics' },
                { label: 'Pedidos', value: orders.length.toString(), sub: 'pendentes', color: '#f59e0b', path: '/seller/orders' },
                { label: 'Produtos', value: ACTIVE_PRODUCTS.filter(p => p.status === 'active').length.toString(), sub: 'activos', color: '#059669', path: '/seller/products' },
              ].map(stat => (
                <button key={stat.label} onClick={() => navigate(stat.path)}
                  style={{ flex: 1, background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: '12px 10px', textAlign: 'center', cursor: 'pointer' }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 16, fontWeight: 700, color: stat.color }}>{stat.value}</p>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A', marginTop: 2 }}>{stat.sub}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Action items */}
          <div style={{ padding: '20px 16px 0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h2 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#FFFFFF' }}>Requer atenção</h2>
              {orders.length > 0 && (
                <div style={{ background: '#dc2626', borderRadius: 20, padding: '2px 8px' }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 700, color: '#FFFFFF' }}>{orders.length}</span>
                </div>
              )}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {ACTION_ITEMS.map(item => (
                <button key={item.type} onClick={() => navigate(item.path)}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', borderRadius: 12, cursor: 'pointer', background: item.bg, border: `1px solid ${item.color}30`, textAlign: 'left' }}>
                  <div style={{ width: 36, height: 36, borderRadius: 10, background: item.color + '20', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, position: 'relative' }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={item.color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d={item.icon} />
                    </svg>
                    {item.count > 0 && (
                      <div style={{ position: 'absolute', top: -4, right: -4, width: 16, height: 16, borderRadius: '50%', background: item.color, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, fontWeight: 700, color: '#0A0A0A' }}>{item.count}</span>
                      </div>
                    )}
                  </div>
                  <div>
                    {item.count !== null && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: item.color }}>{item.count}</p>}
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', lineHeight: 1.3 }}>{item.label}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Pending orders */}
          <div style={{ padding: '20px 16px 0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h2 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#FFFFFF' }}>Novos pedidos</h2>
              <button onClick={() => navigate('/seller/orders')}
                style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C', background: 'none', border: 'none', cursor: 'pointer' }}>
                Ver todos →
              </button>
            </div>

            {orders.length === 0 ? (
              <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: '24px 16px', textAlign: 'center' }}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto 10px' }}>
                  <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
                </svg>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>Sem novos pedidos. Ótimo trabalho!</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {orders.map(order => (
                  <div key={order.id} style={{ background: '#141414', borderRadius: 14, border: `1px solid ${order.urgent ? 'rgba(245,158,11,0.3)' : '#1E1E1E'}`, padding: 14, position: 'relative', overflow: 'hidden' }}>
                    {order.urgent && <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: '#f59e0b' }} />}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#C9A84C' }}>{order.id}</span>
                        {order.urgent && <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, fontWeight: 600, color: '#f59e0b', background: 'rgba(245,158,11,0.1)', padding: '2px 6px', borderRadius: 10 }}>URGENTE</span>}
                      </div>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>{order.time}</span>
                    </div>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', fontWeight: 500, marginBottom: 4 }}>{order.product} ×{order.qty}</p>
                    <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>👤 {order.buyer}</span>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>📍 {order.province}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 16, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(order.total)}</span>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button onClick={() => rejectOrder(order.id)}
                          style={{ padding: '8px 14px', borderRadius: 10, border: '1px solid rgba(220,38,38,0.3)', background: 'rgba(220,38,38,0.08)', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 500, color: '#dc2626', cursor: 'pointer' }}>
                          Rejeitar
                        </button>
                        <button onClick={() => confirmOrder(order.id)}
                          style={{ padding: '8px 14px', borderRadius: 10, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
                          Confirmar
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Product listings */}
          <div style={{ padding: '20px 16px 0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h2 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#FFFFFF' }}>Os seus produtos</h2>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => navigate('/seller/product/new')}
                  style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px', borderRadius: 8, background: '#C9A84C', border: 'none', cursor: 'pointer' }}>
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 700, color: '#0A0A0A' }}>Novo</span>
                </button>
                <button onClick={() => navigate('/seller/products')}
                  style={{ padding: '5px 10px', borderRadius: 8, border: '1px solid #2A2A2A', background: 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', cursor: 'pointer' }}>
                  Ver todos
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {ACTIVE_PRODUCTS.map(product => (
                <div key={product.id} style={{ background: '#141414', borderRadius: 14, border: `1px solid ${product.status === 'out_of_stock' ? 'rgba(220,38,38,0.2)' : '#1E1E1E'}`, padding: 14, display: 'flex', gap: 12, alignItems: 'center' }}>
                  <div style={{ width: 56, height: 56, borderRadius: 10, background: product.image_color, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
                    </svg>
                    {product.status === 'out_of_stock' && (
                      <div style={{ position: 'absolute', inset: 0, borderRadius: 10, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 7, fontWeight: 700, color: '#dc2626', textAlign: 'center', lineHeight: 1.3 }}>SEM{'\n'}STOCK</span>
                      </div>
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: '#FFFFFF', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{product.name}</p>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: '#C9A84C', marginBottom: 4 }}>{formatPrice(product.price)}</p>
                    <div style={{ display: 'flex', gap: 10 }}>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: product.stock <= 3 ? '#dc2626' : '#9A9A9A' }}>
                        📦 {product.stock === 0 ? 'Esgotado' : `${product.stock} em stock`}
                      </span>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>🛒 {product.sales}</span>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>👁 {product.views}</span>
                    </div>
                  </div>
                  <button onClick={() => navigate('/seller/products')}
                    style={{ width: 32, height: 32, borderRadius: 8, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>
    </SellerLayout>
  )
}
