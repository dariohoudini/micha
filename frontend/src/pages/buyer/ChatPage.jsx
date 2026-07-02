import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import BuyerLayout from '@/layouts/BuyerLayout'
import { chatApi } from '@/api/chat'
import { useAuthStore } from '@/stores/authStore'
import { asList } from '@/lib/asList'

function ConvSkeleton() {
  return (
    <div style={{ display: 'flex', gap: 12, padding: '14px 16px', alignItems: 'center' }}>
      <div className="skeleton" style={{ width: 52, height: 52, borderRadius: '50%', flexShrink: 0 }} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div className="skeleton" style={{ height: 13, width: '55%', borderRadius: 6 }} />
        <div className="skeleton" style={{ height: 11, width: '80%', borderRadius: 5 }} />
      </div>
    </div>
  )
}

function timeAgo(dateStr) {
  if (!dateStr) return ''
  const diff = (Date.now() - new Date(dateStr)) / 1000
  if (diff < 60) return 'agora'
  if (diff < 3600) return `${Math.floor(diff / 60)}m`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`
  return `${Math.floor(diff / 86400)}d`
}

export default function ChatPage() {
  const navigate = useNavigate()
  const userId = useAuthStore(s => s.user?.id)
  const [conversations, setConversations] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [error, setError] = useState(null)

  useEffect(() => {
    chatApi.listConversations()
      .then(r => setConversations(asList(r.data)))
      .catch(() => setError('Não foi possível carregar as mensagens.'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = conversations.filter(c => {
    if (!search) return true
    const other = c.participants?.find(p => p.id !== userId)
    return other?.full_name?.toLowerCase().includes(search.toLowerCase())
      || other?.username?.toLowerCase().includes(search.toLowerCase())
  })

  const totalUnread = conversations.reduce((a, c) => a + (c.unread_count || 0), 0)

  return (
    <BuyerLayout>
      <div style={{ padding: 'max(52px, env(safe-area-inset-top)) 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 24, fontWeight: 700, color: '#FFFFFF' }}>Mensagens</h1>
            {totalUnread > 0 && (
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C', marginTop: 2 }}>
                {totalUnread} não lida{totalUnread !== 1 ? 's' : ''}
              </p>
            )}
          </div>
          <button style={{ width: 38, height: 38, borderRadius: 12, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 14, padding: '10px 14px', marginBottom: 16 }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Pesquisar conversas..."
            style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF' }} />
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => <ConvSkeleton key={i} />)
        ) : error ? (
          <div style={{ padding: '40px 24px', textAlign: 'center' }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A' }}>{error}</p>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60%', gap: 16, padding: '0 32px' }}>
            <div style={{ width: 72, height: 72, borderRadius: 18, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
            </div>
            <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF', textAlign: 'center' }}>
              {search ? 'Sem resultados' : 'Sem conversas'}
            </h2>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', textAlign: 'center', lineHeight: 1.5 }}>
              {search ? 'Tenta pesquisar outro nome.' : 'Contacta um vendedor num produto para iniciar uma conversa.'}
            </p>
          </div>
        ) : (
          filtered.map((conv, i) => {
            const other = conv.participants?.find(p => p.id !== userId) || {}
            const initials = (other.full_name || other.username || '?').slice(0, 2).toUpperCase()
            const lastMsg = conv.last_message
            const unread = conv.unread_count || 0

            return (
              <button
                key={conv.id}
                onClick={() => navigate(`/chat/${conv.id}`)}
                style={{
                  display: 'flex', gap: 12, padding: '14px 16px', alignItems: 'center',
                  background: 'transparent', border: 'none', cursor: 'pointer', width: '100%', textAlign: 'left',
                  borderBottom: i < filtered.length - 1 ? '1px solid #1E1E1E' : 'none',
                }}
              >
                <div style={{ position: 'relative', flexShrink: 0 }}>
                  <div style={{ width: 52, height: 52, borderRadius: '50%', background: 'linear-gradient(135deg, #C9A84C, #A67C35)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                    {other.avatar
                      ? <img src={other.avatar} alt={initials} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      : <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 17, fontWeight: 700, color: '#0A0A0A' }}>{initials}</span>
                    }
                  </div>
                  {conv.is_online && (
                    <div style={{ position: 'absolute', bottom: 1, right: 1, width: 12, height: 12, borderRadius: '50%', background: '#059669', border: '2px solid #0A0A0A' }} />
                  )}
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: unread > 0 ? 700 : 500, color: '#FFFFFF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '65%' }}>
                      {other.full_name || other.username || 'Utilizador'}
                    </span>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: unread > 0 ? '#C9A84C' : '#9A9A9A', flexShrink: 0 }}>
                      {timeAgo(lastMsg?.created_at)}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: unread > 0 ? '#CCCCCC' : '#9A9A9A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, marginRight: 8 }}>
                      {lastMsg?.content || 'Inicia uma conversa'}
                    </p>
                    {unread > 0 && (
                      <div style={{ minWidth: 20, height: 20, borderRadius: 10, background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 5px', flexShrink: 0 }}>
                        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 700, color: '#0A0A0A' }}>{unread > 99 ? '99+' : unread}</span>
                      </div>
                    )}
                  </div>
                </div>
              </button>
            )
          })
        )}
      </div>
    </BuyerLayout>
  )
}
