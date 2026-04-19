import { useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

const SELLER_NAV = [
  { path: '/seller',           label: 'Painel',    icon: 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 22V12h6v10' },
  { path: '/seller/products',  label: 'Produtos',  icon: 'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z' },
  { path: '/seller/orders',    label: 'Pedidos',   icon: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2', badge: 3 },
  { path: '/seller/chat',      label: 'Chat',      icon: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z', badge: 3 },
  { path: '/seller/analytics', label: 'Análises',  icon: 'M18 20V10M12 20V4M6 20v-6' },
  { path: '/seller/wallet',    label: 'Carteira',  icon: 'M21 12V7H5a2 2 0 0 1 0-4h14v4M3 5v14a2 2 0 0 0 2 2h16v-5' },
  { path: '/seller/setup',     label: 'Loja',      icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 0 0-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 0 0-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z' },
]

export default function SellerLayout({ children, title, showBack = false }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()

  const isActive = (path) => {
    if (path === '/seller') return pathname === '/seller'
    return pathname.startsWith(path)
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0F0F0F', overflow: 'hidden' }}>

      {/* Top bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 'max(48px, env(safe-area-inset-top)) 16px 12px', background: '#0F0F0F', borderBottom: '1px solid #1A1A1A', flexShrink: 0, gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
          {showBack && (
            <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, flexShrink: 0 }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 12H5M12 5l-7 7 7 7" />
              </svg>
            </button>
          )}
          <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 16, fontWeight: 700, color: '#C9A84C' }}>M</span>
          <div style={{ width: 1, height: 14, background: '#2A2A2A' }} />
          <h1 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 600, color: '#FFFFFF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {title || 'Centro de Vendas'}
          </h1>
        </div>

        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          <button onClick={() => navigate('/seller/chat')} style={{ position: 'relative', width: 34, height: 34, borderRadius: 10, background: '#1A1A1A', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <div style={{ position: 'absolute', top: -3, right: -3, width: 14, height: 14, borderRadius: '50%', background: '#6366f1', border: '1.5px solid #0F0F0F', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ fontSize: 8, fontWeight: 700, color: '#FFFFFF' }}>3</span>
            </div>
          </button>

          <button onClick={() => navigate('/home')} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '6px 10px', borderRadius: 20, background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.25)', cursor: 'pointer' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" /><line x1="3" y1="6" x2="21" y2="6" /><path d="M16 10a4 4 0 0 1-8 0" />
            </svg>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: '#C9A84C' }}>Comprar</span>
          </button>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {children}
      </div>

      {/* Bottom nav */}
      <nav style={{ display: 'flex', alignItems: 'center', background: '#0F0F0F', borderTop: '1px solid #1A1A1A', paddingTop: 8, paddingBottom: 'max(20px, env(safe-area-inset-bottom))', flexShrink: 0 }}>
        {SELLER_NAV.map(tab => {
          const active = isActive(tab.path)
          return (
            <button key={tab.path} onClick={() => navigate(tab.path)}
              aria-label={tab.label} aria-current={active ? 'page' : undefined}
              style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0', position: 'relative' }}>
              <div style={{ position: 'relative' }}>
                <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke={active ? '#C9A84C' : '#444'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d={tab.icon} />
                </svg>
                {tab.badge > 0 && (
                  <div style={{ position: 'absolute', top: -4, right: -5, width: 14, height: 14, borderRadius: '50%', background: tab.path === '/seller/chat' ? '#6366f1' : '#f59e0b', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1.5px solid #0F0F0F' }}>
                    <span style={{ fontSize: 8, fontWeight: 700, color: '#FFFFFF' }}>{tab.badge}</span>
                  </div>
                )}
              </div>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 8, fontWeight: active ? 600 : 400, color: active ? '#C9A84C' : '#444' }}>
                {tab.label}
              </span>
              {active && <div style={{ position: 'absolute', bottom: -2, width: 3, height: 3, borderRadius: '50%', background: '#C9A84C' }} />}
            </button>
          )
        })}
      </nav>
    </div>
  )
}
