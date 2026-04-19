import { useNavigate, useLocation } from 'react-router-dom'
import { useCartStore } from '@/stores/cartStore'

const TABS = [
  {
    path: '/home', label: 'Início',
    icon: 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 22V12h6v10',
  },
  {
    path: '/explore', label: 'Explorar',
    icon: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.35-4.35',
  },
  {
    path: '/cart', label: 'Carrinho',
    icon: 'M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4zM3 6h18M16 10a4 4 0 0 1-8 0',
    badge: 'cart',
  },
  {
    path: '/chat', label: 'Mensagens',
    icon: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
    badge: 'chat',
  },
  {
    path: '/profile', label: 'Perfil',
    icon: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
  },
]

// Mock unread count — replace with real store
const CHAT_UNREAD = 2

function BottomNav() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const totalItems = useCartStore(s => s.items.reduce((a, i) => a + i.quantity, 0))

  const isActive = (path) => {
    if (path === '/chat') return pathname.startsWith('/chat')
    return pathname.startsWith(path)
  }

  const getBadge = (tab) => {
    if (tab.badge === 'cart') return totalItems > 0 ? totalItems : null
    if (tab.badge === 'chat') return CHAT_UNREAD > 0 ? CHAT_UNREAD : null
    return null
  }

  return (
    <nav style={{
      display: 'flex', alignItems: 'center',
      background: '#0A0A0A',
      borderTop: '1px solid #1E1E1E',
      paddingTop: 10,
      paddingBottom: 'max(24px, env(safe-area-inset-bottom))',
      flexShrink: 0, width: '100%',
    }}>
      {TABS.map(tab => {
        const active = isActive(tab.path)
        const badge = getBadge(tab)
        return (
          <button
            key={tab.path}
            onClick={() => navigate(tab.path)}
            aria-label={tab.label}
            aria-current={active ? 'page' : undefined}
            style={{
              flex: 1, display: 'flex', flexDirection: 'column',
              alignItems: 'center', gap: 4,
              background: 'none', border: 'none',
              cursor: 'pointer', padding: '4px 0',
              position: 'relative',
            }}
          >
            <div style={{ position: 'relative' }}>
              <svg
                width="22" height="22" viewBox="0 0 24 24" fill="none"
                stroke={active ? '#C9A84C' : '#9A9A9A'}
                strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d={tab.icon} />
              </svg>
              {badge && (
                <div style={{
                  position: 'absolute', top: -4, right: -6,
                  minWidth: 16, height: 16, borderRadius: 8,
                  background: tab.badge === 'chat' ? '#6366f1' : '#C9A84C',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  border: '1.5px solid #0A0A0A', padding: '0 3px',
                }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, fontWeight: 700, color: '#FFFFFF' }}>
                    {badge > 9 ? '9+' : badge}
                  </span>
                </div>
              )}
            </div>
            <span style={{
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 10, fontWeight: active ? 600 : 400,
              color: active ? '#C9A84C' : '#9A9A9A',
            }}>
              {tab.label}
            </span>
            {active && (
              <div style={{
                position: 'absolute', bottom: -2,
                width: 4, height: 4, borderRadius: '50%',
                background: '#C9A84C',
              }} />
            )}
          </button>
        )
      })}
    </nav>
  )
}

export default function BuyerLayout({ children, hideNav = false }) {
  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      background: '#0A0A0A', overflow: 'hidden',
    }}>
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {children}
      </div>
      {!hideNav && <BottomNav />}
    </div>
  )
}
