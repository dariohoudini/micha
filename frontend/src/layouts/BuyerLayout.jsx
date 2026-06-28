import { useNavigate, useLocation } from 'react-router-dom'
import { useCartStore } from '@/stores/cartStore'
import { useAuthStore } from '@/stores/authStore'
import { requireAuth } from '@/lib/authGate'
import { useUnreadCount } from '@/hooks/useQueries'

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

function BottomNav() {
  const navigate = useNavigate()
  const location = useLocation()
  const { pathname } = location
  const totalItems = useCartStore(s => s.items.reduce((a, i) => a + i.quantity, 0))
  // §34.5 — bell/notification badge is fed from the real unread
  // count API. The hook fetches on mount + app foreground and
  // invalidates when notifications are marked read elsewhere.
  // Falls back to 0 silently on auth/network errors so guest users
  // never see a flickering badge.
  const { data: unreadChat = 0 } = useUnreadCount()

  const isActive = (path) => {
    if (path === '/chat') return pathname.startsWith('/chat')
    return pathname.startsWith(path)
  }

  const getBadge = (tab) => {
    if (tab.badge === 'cart') return totalItems > 0 ? totalItems : null
    if (tab.badge === 'chat') return unreadChat > 0 ? unreadChat : null
    return null
  }

  // §1.1 + §34.1 — Cart / Account tabs are auth-gated. A guest who
  // taps them must be routed to LoginScreen with `returnTo` set so
  // they bounce straight back to the tab after logging in.
  const handleTabPress = (path) => {
    // §1.1 — tapping the active tab on Home scrolls to top instead
    // of pushing a new entry. Approximate by triggering a custom
    // event the HomePage listens to; if no listener, harmless no-op.
    if (path === '/home' && pathname === '/home') {
      try { window.dispatchEvent(new CustomEvent('micha:home-tab-tap')) } catch {}
      try { window.scrollTo({ top: 0, behavior: 'smooth' }) } catch {}
      return
    }
    if (path === '/cart' || path === '/profile') {
      const gated = path === '/cart' ? 'cart_tab' : 'account_tab'
      if (!requireAuth(navigate, location, gated)) return
    }
    navigate(path)
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
            onClick={() => handleTabPress(tab.path)}
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

// Floating "Modo Vendedor" pill — only renders for users with the
// seller flag. Symmetric to SellerLayout's "Comprar" pill, giving
// every buyer screen a one-tap path back to the seller dashboard
// without having to remember the URL or hunt through the profile
// menu. Anchored to the bottom-right just above the BottomNav so it
// doesn't fight with any page that already paints its own top bar
// (HomePage, ExplorePage, ProfilePage). The bottom offset stacks the
// nav height + safe-area inset.
function SellerModeFab({ hideNav }) {
  const navigate = useNavigate()
  const isSeller = useAuthStore(s => s.isSeller)
  if (!isSeller) return null
  // BottomNav height ≈ 60px (padding + icon row). When the nav is
  // hidden, sit closer to the screen edge.
  const bottomOffset = hideNav
    ? 'calc(env(safe-area-inset-bottom) + 16px)'
    : 'calc(env(safe-area-inset-bottom) + 76px)'
  return (
    <button
      onClick={() => navigate('/seller')}
      aria-label="Mudar para modo vendedor"
      style={{
        position: 'fixed',
        bottom: bottomOffset,
        right: 14,
        zIndex: 60,
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '9px 14px',
        borderRadius: 24,
        background: 'rgba(201,168,76,0.95)',
        border: '1px solid rgba(201,168,76,0.6)',
        boxShadow: '0 6px 20px rgba(0,0,0,0.4), 0 0 0 4px rgba(201,168,76,0.08)',
        cursor: 'pointer',
      }}
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
      </svg>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#0A0A0A', letterSpacing: '0.02em' }}>Vender</span>
    </button>
  )
}

export default function BuyerLayout({ children, hideNav = false }) {
  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      background: '#0A0A0A', overflow: 'hidden',
    }}>
      <SellerModeFab hideNav={hideNav} />
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {children}
      </div>
      {!hideNav && <BottomNav />}
    </div>
  )
}
