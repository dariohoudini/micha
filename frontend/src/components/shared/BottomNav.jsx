import { useNavigate, useLocation } from 'react-router-dom'
import { useCartStore as useCart } from '@/stores/cartStore'

const tabs = [
  {
    path: '/home', label: 'Início',
    icon: (active) => (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
        stroke={active ? '#C9A84C' : '#9A9A9A'} strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        <polyline points="9 22 9 12 15 12 15 22" />
      </svg>
    ),
  },
  {
    path: '/explore', label: 'Explorar',
    icon: (active) => (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
        stroke={active ? '#C9A84C' : '#9A9A9A'} strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
  },
  {
    path: '/cart', label: 'Carrinho',
    icon: (active) => (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
        stroke={active ? '#C9A84C' : '#9A9A9A'} strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
        <line x1="3" y1="6" x2="21" y2="6" />
        <path d="M16 10a4 4 0 0 1-8 0" />
      </svg>
    ),
  },
  {
    path: '/profile', label: 'Perfil',
    icon: (active) => (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
        stroke={active ? '#C9A84C' : '#9A9A9A'} strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
    ),
  },
]

export default function BottomNav() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const totalItems = useCart(s => s.items.reduce((a, i) => a + i.quantity, 0))

  return (
    <nav
      className="bottom-nav"
      style={{
        display: 'flex', alignItems: 'center',
        background: '#0A0A0A',
        borderTop: '1px solid #1E1E1E',
        flexShrink: 0,
        paddingTop: 10,
      }}
    >
      {tabs.map(tab => {
        const active = pathname === tab.path
        const isCart = tab.path === '/cart'
        return (
          <button
            key={tab.path}
            onClick={() => navigate(tab.path)}
            style={{
              flex: 1, display: 'flex', flexDirection: 'column',
              alignItems: 'center', gap: 4,
              background: 'none', border: 'none', cursor: 'pointer',
              padding: '4px 0', position: 'relative',
            }}
          >
            <div style={{ position: 'relative' }}>
              {tab.icon(active)}
              {isCart && totalItems > 0 && (
                <div style={{
                  position: 'absolute', top: -4, right: -6,
                  width: 16, height: 16, borderRadius: '50%',
                  background: '#C9A84C',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  border: '1.5px solid #0A0A0A',
                }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 9, fontWeight: 700, color: '#0A0A0A' }}>
                    {totalItems > 9 ? '9+' : totalItems}
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
