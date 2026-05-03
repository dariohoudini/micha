import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import { useAuthStore } from '@/stores/authStore'
import client from '@/api/client'
import { TodaySalesCard, RevenueChart, BestProductsWidget, AIDescriptionGenerator } from '@/components/seller/SellerDashboardUX'
import HelperBot from '@/components/shared/HelperBot'
import { useSellerDashboard, useSellerOrders } from '@/hooks/useQueries'

// Seller AI assistant helper
const askSellerAI = async (message) => {
  try {
    const res = await client.post('/api/v1/ai/chat/', {
      message,
      context: 'seller_assistant',
    })
    return res.data.response || res.data.message || ''
  } catch {
    return 'Não foi possível obter resposta. Tenta novamente.'
  }
}
import { SellerCoachPanel } from '@/components/shared/HelperBot'
import { PayoutScheduleCalendar } from '@/components/shared/MichaUXComponents'


const formatPrice = (n) => Number(n || 0).toLocaleString('pt-AO') + ' Kz'

export default function SellerDashboardPage() {
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)
  const [stats, setStats] = useState(null)
  const [pendingOrders, setPendingOrders] = useState([])
  const [lowStock, setLowStock] = useState([])
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  useEffect(() => { loadDashboard() }, [])

  const loadDashboard = async () => {
    setLoading(true)
    try {
      const [dashRes, ordersRes, productsRes] = await Promise.allSettled([
        client.get('/api/v1/seller/dashboard/'),
        client.get('/api/v1/orders/seller/?status=pending&limit=5'),
        client.get('/api/v1/products/my/?limit=10'),
      ])
      if (dashRes.status === 'fulfilled') setStats(dashRes.value.data)
      if (ordersRes.status === 'fulfilled') setPendingOrders(ordersRes.value.data.results || ordersRes.value.data || [])
      if (productsRes.status === 'fulfilled') {
        const products = productsRes.value.data.results || productsRes.value.data || []
        setLowStock(products.filter(p => (p.stock || 0) <= 5))
      }
    } catch (err) { console.error(err) }
    finally { setLoading(false) }
  }

  const confirmOrder = async (orderId) => {
    try {
      await client.post(`/api/v1/orders/${orderId}/status/`, { status: 'confirmed' })
      setPendingOrders(prev => prev.filter(o => o.id !== orderId))
      showToast('Pedido confirmado!')
    } catch { showToast('Erro ao confirmar.', 'error') }
  }

  const rejectOrder = async (orderId) => {
    try {
      await client.post(`/api/v1/orders/${orderId}/cancel/`, { reason: 'Rejeitado pelo vendedor' })
      setPendingOrders(prev => prev.filter(o => o.id !== orderId))
      showToast('Pedido rejeitado.', 'error')
    } catch { showToast('Erro ao rejeitar.', 'error') }
  }

  const S = { fontFamily: "'DM Sans', sans-serif" }

  return (
    <SellerLayout title="Centro de Vendas">
      {/* Real dashboard components */}
      <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <TodaySalesCard />
        <RevenueChart />
        <BestProductsWidget />
      </div>

      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#fff', padding: '10px 20px', borderRadius: 12, ...S, fontSize: 13, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap' }}>
          {toast.msg}
        </div>
      )}
      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>

          <div>
            <p style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>Bem-vindo de volta</p>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF' }}>
              {user?.username || user?.email?.split('@')[0]}
            </h1>
          </div>

          {/* Stats */}
          {loading ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {[0,1,2,3].map(i => <div key={i} style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', height: 80 }} />)}
            </div>
          ) : stats && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {[
                { label: 'Vendas hoje', value: formatPrice(stats.revenue_today), color: '#C9A84C' },
                { label: 'Pedidos hoje', value: stats.orders_today || 0, color: '#FFFFFF' },
                { label: 'Total produtos', value: stats.total_products || 0, color: '#FFFFFF' },
                { label: 'Avaliação', value: stats.avg_rating ? `★ ${Number(stats.avg_rating).toFixed(1)}` : '—', color: '#C9A84C' },
              ].map(stat => (
                <div key={stat.label} style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 14 }}>
                  <p style={{ ...S, fontSize: 22, fontWeight: 700, color: stat.color, marginBottom: 4 }}>{stat.value}</p>
                  <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>{stat.label}</p>
                </div>
              ))}
            </div>
          )}

          {/* Quick actions */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {[
              { label: 'Pedidos pendentes', count: pendingOrders.length, color: '#f59e0b', path: '/seller/orders', icon: '📋' },
              { label: 'Stock baixo', count: lowStock.length, color: '#dc2626', path: '/seller/products', icon: '⚠️' },
              { label: 'Ver análises', count: null, color: '#C9A84C', path: '/seller/analytics', icon: '📊' },
              { label: 'Novo produto', count: null, color: '#059669', path: '/seller/products/new', icon: '+' },
            ].map(action => (
              <button key={action.label} onClick={() => navigate(action.path)}
                style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 14, textAlign: 'left', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 20 }}>{action.icon}</span>
                  {action.count !== null && <span style={{ ...S, fontSize: 18, fontWeight: 700, color: action.color }}>{action.count}</span>}
                </div>
                <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>{action.label}</p>
              </button>
            ))}
          </div>

          {/* Pending orders */}
          {pendingOrders.length > 0 && (
            <div>
              <h2 style={{ ...S, fontSize: 14, fontWeight: 700, color: '#FFFFFF', marginBottom: 10 }}>🔔 A confirmar ({pendingOrders.length})</h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {pendingOrders.map(order => (
                  <div key={order.id} style={{ background: '#141414', borderRadius: 14, border: '1px solid rgba(245,158,11,0.3)', padding: 14 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                      <span style={{ ...S, fontSize: 12, fontWeight: 700, color: '#C9A84C' }}>#{String(order.id).slice(-8).toUpperCase()}</span>
                      <span style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>{new Date(order.created_at).toLocaleTimeString('pt-AO', { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                    <p style={{ ...S, fontSize: 13, color: '#FFFFFF', marginBottom: 4 }}>{order.items?.[0]?.product_name || 'Produto'}</p>
                    <p style={{ ...S, fontSize: 14, fontWeight: 700, color: '#C9A84C', marginBottom: 10 }}>{formatPrice(order.total)}</p>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => confirmOrder(order.id)}
                        style={{ flex: 1, padding: '9px 0', borderRadius: 10, border: 'none', background: '#C9A84C', ...S, fontSize: 12, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
                        ✓ Confirmar
                      </button>
                      <button onClick={() => rejectOrder(order.id)}
                        style={{ flex: 1, padding: '9px 0', borderRadius: 10, border: '1px solid rgba(220,38,38,0.3)', background: 'transparent', ...S, fontSize: 12, color: '#dc2626', cursor: 'pointer' }}>
                        ✕ Rejeitar
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Low stock */}
          {lowStock.length > 0 && (
            <div>
              <h2 style={{ ...S, fontSize: 14, fontWeight: 700, color: '#FFFFFF', marginBottom: 10 }}>⚠️ Stock baixo</h2>
              {lowStock.slice(0, 3).map(p => (
                <button key={p.id} onClick={() => navigate(`/seller/products`)}
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(220,38,38,0.2)', background: 'rgba(220,38,38,0.05)', cursor: 'pointer', marginBottom: 8 }}>
                  <span style={{ ...S, fontSize: 13, color: '#FFFFFF' }}>{p.name}</span>
                  <span style={{ ...S, fontSize: 12, fontWeight: 700, color: p.stock === 0 ? '#dc2626' : '#f59e0b' }}>
                    {p.stock === 0 ? 'Esgotado' : `${p.stock} restantes`}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    
      <HelperBot screen="dashboard" isSeller={true} />
      </SellerLayout>
  )
}
