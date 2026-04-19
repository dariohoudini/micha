import { useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

const ADMIN_NAV = [
  { path: '/admin',          label: 'Dashboard', icon: 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 22V12h6v10' },
  { path: '/admin/users',    label: 'Usuários',  icon: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z' },
  { path: '/admin/sellers',  label: 'Vendedores',icon: 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 22V12h6v10' },
  { path: '/admin/orders',   label: 'Pedidos',   icon: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2' },
  { path: '/admin/products', label: 'Produtos',  icon: 'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z' },
  { path: '/admin/chat',     label: 'Chat',      icon: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z', badge: 2 },
  { path: '/admin/settings', label: 'Config',    icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 0 0-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 0 0-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z' },
]

const ADMIN_COLORS = {
  bg: '#060608', surface: '#0D0D1A', card: '#111120',
  border: '#1A1A2E', text: '#E2E8F0', muted: '#64748B',
  accent: '#6366F1', accentLight: 'rgba(99,102,241,0.1)', accentBorder: 'rgba(99,102,241,0.25)',
}

export { ADMIN_COLORS }

export default function AdminLayout({ children, title, showBack = false }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const logout = useAuthStore(s => s.logout)

  const isActive = (path) => {
    if (path === '/admin') return pathname === '/admin'
    return pathname.startsWith(path)
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: ADMIN_COLORS.bg, overflow: 'hidden', fontFamily: "'DM Sans', sans-serif" }}>

      {/* Top bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 'max(48px, env(safe-area-inset-top)) 16px 12px', background: `linear-gradient(135deg, ${ADMIN_COLORS.surface} 0%, ${ADMIN_COLORS.bg} 100%)`, borderBottom: `1px solid ${ADMIN_COLORS.border}`, flexShrink: 0, gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
          {showBack && (
            <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, flexShrink: 0 }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={ADMIN_COLORS.text} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 12H5M12 5l-7 7 7 7" />
              </svg>
            </button>
          )}
          <div style={{ background: 'linear-gradient(135deg, #6366f1, #4f46e5)', borderRadius: 8, padding: '3px 8px', flexShrink: 0 }}>
            <span style={{ fontSize: 9, fontWeight: 700, color: '#FFFFFF', letterSpacing: '0.12em' }}>ADMIN</span>
          </div>
          <h1 style={{ fontSize: 15, fontWeight: 600, color: ADMIN_COLORS.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {title || 'MICHA Control'}
          </h1>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          <button onClick={() => navigate('/home')}
            style={{ padding: '5px 10px', borderRadius: 8, background: ADMIN_COLORS.accentLight, border: `1px solid ${ADMIN_COLORS.accentBorder}`, fontSize: 11, color: '#818cf8', cursor: 'pointer' }}>
            Ver loja
          </button>
          <button onClick={async () => { await logout(); navigate('/login') }}
            style={{ padding: '5px 10px', borderRadius: 8, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', fontSize: 11, color: '#f87171', cursor: 'pointer' }}>
            Sair
          </button>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {children}
      </div>

      {/* Admin bottom nav - scrollable for 7 tabs */}
      <nav style={{ display: 'flex', alignItems: 'center', background: ADMIN_COLORS.surface, borderTop: `1px solid ${ADMIN_COLORS.border}`, paddingTop: 8, paddingBottom: 'max(20px, env(safe-area-inset-bottom))', flexShrink: 0, overflowX: 'auto', scrollbarWidth: 'none' }}>
        {ADMIN_NAV.map(tab => {
          const active = isActive(tab.path)
          return (
            <button key={tab.path} onClick={() => navigate(tab.path)}
              aria-label={tab.label} aria-current={active ? 'page' : undefined}
              style={{ flex: '0 0 auto', minWidth: 52, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, background: 'none', border: 'none', cursor: 'pointer', padding: '4px 6px', position: 'relative' }}>
              <div style={{ position: 'relative' }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={active ? '#818cf8' : '#374151'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d={tab.icon} />
                </svg>
                {tab.badge > 0 && (
                  <div style={{ position: 'absolute', top: -4, right: -5, width: 14, height: 14, borderRadius: '50%', background: '#ef4444', display: 'flex', alignItems: 'center', justifyContent: 'center', border: `1.5px solid ${ADMIN_COLORS.surface}` }}>
                    <span style={{ fontSize: 8, fontWeight: 700, color: '#FFFFFF' }}>{tab.badge}</span>
                  </div>
                )}
              </div>
              <span style={{ fontSize: 8, fontWeight: active ? 600 : 400, color: active ? '#818cf8' : '#374151', whiteSpace: 'nowrap' }}>
                {tab.label}
              </span>
              {active && <div style={{ position: 'absolute', bottom: -2, width: 3, height: 3, borderRadius: '50%', background: '#6366f1' }} />}
            </button>
          )
        })}
      </nav>
    </div>
  )
}
