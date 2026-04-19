import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import { MOCK_CONVERSATIONS } from '@/components/chat/useChat'
import { formatPrice } from '@/components/buyer/mockData'

export default function ChatPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')

  const filtered = MOCK_CONVERSATIONS.filter(c =>
    !search || c.participant.name.toLowerCase().includes(search.toLowerCase())
  )

  const totalUnread = MOCK_CONVERSATIONS.reduce((a, c) => a + c.unread, 0)

  return (
    <BuyerLayout>
      {/* Header */}
      <div style={{ padding: '52px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: '#FFFFFF' }}>
              Mensagens
            </h1>
            {totalUnread > 0 && (
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C', marginTop: 2 }}>
                {totalUnread} mensagem{totalUnread !== 1 ? 's' : ''} não lida{totalUnread !== 1 ? 's' : ''}
              </p>
            )}
          </div>
          <button style={{ width: 38, height: 38, borderRadius: 12, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </button>
        </div>

        {/* Search */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 14, padding: '10px 14px', marginBottom: 16 }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Pesquisar conversas..."
            style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF' }} />
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {filtered.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60%', gap: 16, padding: '0 32px' }}>
            <div style={{ width: 72, height: 72, borderRadius: 18, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF', textAlign: 'center' }}>
              Sem conversas
            </h2>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center' }}>
              As suas conversas com vendedores aparecerão aqui. Comece por explorar produtos.
            </p>
            <button className="btn-primary" onClick={() => navigate('/explore')} style={{ marginTop: 4 }}>
              Explorar produtos
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {filtered.map((conv, i) => (
              <button key={conv.id}
                onClick={() => navigate(`/chat/${conv.id}`)}
                style={{ display: 'flex', gap: 14, padding: '14px 16px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', borderBottom: '1px solid #141414', transition: 'background 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.background = '#0F0F0F'}
                onMouseLeave={e => e.currentTarget.style.background = 'none'}
              >
                {/* Avatar */}
                <div style={{ position: 'relative', flexShrink: 0 }}>
                  <div style={{ width: 52, height: 52, borderRadius: '50%', background: 'linear-gradient(135deg, #C9A84C, #A67C35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#0A0A0A' }}>
                      {conv.participant.avatar}
                    </span>
                  </div>
                  {/* Online indicator */}
                  {conv.online && (
                    <div style={{ position: 'absolute', bottom: 2, right: 2, width: 12, height: 12, borderRadius: '50%', background: '#059669', border: '2px solid #0A0A0A' }} />
                  )}
                </div>

                {/* Content */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: conv.unread > 0 ? 700 : 500, color: '#FFFFFF' }}>
                        {conv.participant.name}
                      </span>
                      {conv.participant.verified && (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="#C9A84C">
                          <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      )}
                    </div>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: conv.unread > 0 ? '#C9A84C' : '#9A9A9A' }}>
                      {conv.lastTime}
                    </span>
                  </div>

                  {/* Product context */}
                  {conv.product && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                      <div style={{ width: 16, height: 16, borderRadius: 4, background: conv.product.image_color, flexShrink: 0 }} />
                      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#C9A84C', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {conv.product.name}
                      </span>
                    </div>
                  )}

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                      {conv.lastMessage}
                    </span>
                    {conv.unread > 0 && (
                      <div style={{ width: 20, height: 20, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginLeft: 8 }}>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 700, color: '#0A0A0A' }}>
                          {conv.unread}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </BuyerLayout>
  )
}
