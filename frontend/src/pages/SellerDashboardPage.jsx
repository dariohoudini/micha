import { useNavigate } from 'react-router-dom'
import { useAuthStore as useAuth } from '@/stores/authStore'

const STATS = [
  { label: 'Vendas hoje', value: '0 Kz', icon: 'M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6', color: '#C9A84C' },
  { label: 'Pedidos', value: '0', icon: 'M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4zM3 6h18', color: '#3b82f6' },
  { label: 'Produtos', value: '0', icon: 'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z', color: '#059669' },
  { label: 'Avaliação', value: '—', icon: 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z', color: '#f59e0b' },
]

const QUICK_ACTIONS = [
  { label: 'Adicionar produto', icon: 'M12 5v14M5 12h14', path: '/seller/product/new', color: '#C9A84C' },
  { label: 'Ver pedidos', icon: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2', path: '/seller/orders', color: '#3b82f6' },
  { label: 'Carteira', icon: 'M21 12V7H5a2 2 0 0 1 0-4h14v4M3 5v14a2 2 0 0 0 2 2h16v-5', path: '/seller/wallet', color: '#059669' },
  { label: 'Configurar loja', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 0 0-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 0 0-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z', path: '/seller/setup', color: '#8b5cf6' },
]

export default function SellerDashboardPage() {
  const navigate = useNavigate()
  const user = useAuth(s => s.user)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      <div className="screen" style={{ flex: 1 }}>

        {/* Header */}
        <div style={{ padding: '52px 16px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <button onClick={() => navigate('/profile')}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 0 8px', display: 'flex', alignItems: 'center', gap: 6 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M19 12H5M12 5l-7 7 7 7" />
                </svg>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A' }}>Perfil</span>
              </button>
              <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: '#FFFFFF' }}>
                Painel de Vendedor
              </h1>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginTop: 4 }}>
                {user?.email}
              </p>
            </div>
            {/* Store status badge */}
            <div style={{
              padding: '6px 12px', borderRadius: 20,
              background: 'rgba(5,150,105,0.1)', border: '1px solid rgba(5,150,105,0.3)',
            }}>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: '#059669' }}>
                Activo
              </span>
            </div>
          </div>
        </div>

        {/* Stats grid */}
        <div style={{ padding: '0 16px', marginBottom: 24 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {STATS.map(stat => (
              <div key={stat.label} style={{
                background: '#141414', borderRadius: 16,
                border: '1px solid #1E1E1E', padding: 16,
              }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 10,
                  background: `${stat.color}15`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  marginBottom: 12,
                }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                    stroke={stat.color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d={stat.icon} />
                  </svg>
                </div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF', marginBottom: 4 }}>
                  {stat.value}
                </p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>
                  {stat.label}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Quick actions */}
        <div style={{ padding: '0 16px', marginBottom: 24 }}>
          <h2 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 12 }}>
            Ações rápidas
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {QUICK_ACTIONS.map(action => (
              <button key={action.label} onClick={() => navigate(action.path)}
                style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
                  padding: 16, borderRadius: 16, cursor: 'pointer', textAlign: 'left',
                  background: '#141414', border: '1px solid #1E1E1E',
                  transition: 'border-color 0.2s',
                }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 10,
                  background: `${action.color}15`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  marginBottom: 10,
                }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                    stroke={action.color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d={action.icon} />
                  </svg>
                </div>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: '#FFFFFF', lineHeight: 1.3 }}>
                  {action.label}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Recent orders placeholder */}
        <div style={{ padding: '0 16px 32px' }}>
          <h2 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 12 }}>
            Pedidos recentes
          </h2>
          <div style={{
            background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E',
            padding: 32, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
          }}>
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2" />
            </svg>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', textAlign: 'center' }}>
              Ainda não tem pedidos. Adicione produtos à sua loja.
            </p>
            <button className="btn-primary" onClick={() => navigate('/seller/product/new')}
              style={{ marginTop: 4, padding: '10px 24px', width: 'auto' }}>
              Adicionar produto
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
