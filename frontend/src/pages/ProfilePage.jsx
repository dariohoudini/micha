import { useNavigate } from 'react-router-dom'
import { useAuthStore as useAuth } from '@/stores/authStore'
import BottomNav from '@/components/shared/BottomNav'

const MENU_SECTIONS = [
  {
    title: 'Conta',
    items: [
      { icon: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', label: 'Editar perfil', path: '/profile/edit' },
      { icon: 'M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4zM3 6h18M16 10a4 4 0 0 1-8 0', label: 'Os meus pedidos', path: '/orders' },
      { icon: 'M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z', label: 'Lista de desejos', path: '/wishlist' },
      { icon: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75', label: 'Referências & Amigos', path: '/referral' },
    ],
  },
  {
    title: 'Vendedor',
    items: [
      { icon: 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 22V12h6v10', label: 'Painel de Vendedor', path: '/seller' },
      { icon: 'M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6', label: 'Carteira & Pagamentos', path: '/seller/wallet' },
    ],
  },
  {
    title: 'Suporte',
    items: [
      { icon: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z', label: 'Chat & Suporte', path: '/chat' },
      { icon: 'M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0', label: 'Notificações', path: '/notifications' },
      { icon: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z', label: 'Privacidade & Segurança', path: '/security' },
    ],
  },
]

export default function ProfilePage() {
  const navigate = useNavigate()
  const user = useAuth(s => s.user); const logout = useAuth(s => s.logout)

  const initial = user?.email?.[0]?.toUpperCase() || 'U'
  const email = user?.email || ''

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>

      <div className="screen" style={{ flex: 1 }}>
        {/* Profile header */}
        <div style={{
          padding: '52px 20px 24px',
          background: 'linear-gradient(180deg, #141414 0%, #0A0A0A 100%)',
          borderBottom: '1px solid #1E1E1E',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {/* Avatar */}
            <div style={{
              width: 68, height: 68, borderRadius: '50%',
              background: 'linear-gradient(135deg, #C9A84C, #A67C35)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              <span style={{
                fontFamily: "'Playfair Display', serif",
                fontSize: 26, fontWeight: 700, color: '#0A0A0A',
              }}>
                {initial}
              </span>
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
              <h2 style={{
                fontFamily: "'Playfair Display', serif",
                fontSize: 20, fontWeight: 700, color: '#FFFFFF',
                marginBottom: 4,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {user?.username || email.split('@')[0]}
              </h2>
              <p style={{
                fontFamily: "'DM Sans', sans-serif",
                fontSize: 12, color: '#9A9A9A',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {email}
              </p>
            </div>

            <button
              onClick={() => navigate('/profile/edit')}
              style={{
                width: 36, height: 36, borderRadius: 10,
                background: '#1E1E1E', border: '1px solid #2A2A2A',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', flexShrink: 0,
              }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>
          </div>

          {/* Stats */}
          <div style={{ display: 'flex', gap: 0, marginTop: 20, background: '#1E1E1E', borderRadius: 14, overflow: 'hidden' }}>
            {[
              { label: 'Pedidos', value: '0' },
              { label: 'Pontos', value: '0' },
              { label: 'Avaliações', value: '0' },
            ].map((stat, i) => (
              <div key={stat.label} style={{
                flex: 1, padding: '12px 0', textAlign: 'center',
                borderRight: i < 2 ? '1px solid #2A2A2A' : 'none',
              }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 18, fontWeight: 700, color: '#C9A84C' }}>{stat.value}</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>{stat.label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Menu sections */}
        <div style={{ padding: '8px 16px 0' }}>
          {MENU_SECTIONS.map(section => (
            <div key={section.title} style={{ marginBottom: 8 }}>
              <p style={{
                fontFamily: "'DM Sans', sans-serif",
                fontSize: 11, fontWeight: 600, color: '#9A9A9A',
                letterSpacing: '0.1em', textTransform: 'uppercase',
                padding: '16px 4px 8px',
              }}>
                {section.title}
              </p>
              <div style={{ background: '#141414', borderRadius: 16, border: '1px solid #1E1E1E', overflow: 'hidden' }}>
                {section.items.map((item, i) => (
                  <button
                    key={item.label}
                    onClick={() => navigate(item.path)}
                    style={{
                      width: '100%', display: 'flex', alignItems: 'center', gap: 14,
                      padding: '14px 16px',
                      background: 'none', border: 'none', cursor: 'pointer',
                      borderBottom: i < section.items.length - 1 ? '1px solid #1E1E1E' : 'none',
                      textAlign: 'left',
                    }}>
                    <div style={{
                      width: 36, height: 36, borderRadius: 10,
                      background: '#1E1E1E',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexShrink: 0,
                    }}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                        stroke="#C9A84C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <path d={item.icon} />
                      </svg>
                    </div>
                    <span style={{
                      fontFamily: "'DM Sans', sans-serif",
                      fontSize: 14, color: '#FFFFFF', flex: 1,
                    }}>
                      {item.label}
                    </span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                      stroke="#2A2A2A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M9 18l6-6-6-6" />
                    </svg>
                  </button>
                ))}
              </div>
            </div>
          ))}

          {/* Logout */}
          <div style={{ marginTop: 8, marginBottom: 24 }}>
            <button
              onClick={handleLogout}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 14,
                padding: '14px 16px', borderRadius: 16,
                background: 'rgba(220,38,38,0.06)',
                border: '1px solid rgba(220,38,38,0.15)',
                cursor: 'pointer', textAlign: 'left',
              }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                background: 'rgba(220,38,38,0.1)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                  stroke="#dc2626" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
                </svg>
              </div>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#dc2626', fontWeight: 500 }}>
                Terminar sessão
              </span>
            </button>
          </div>
        </div>
      </div>

      <BottomNav />
    </div>
  )
}
