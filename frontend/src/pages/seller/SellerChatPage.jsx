import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import { chatApi } from '@/api/chat'
import { useChatWS } from '@/hooks/useChatWS'

const S = { fontFamily: "'DM Sans', sans-serif" }

const timeAgo = (iso) => {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso)
  const m = Math.floor(diff / 60_000)
  if (m < 1) return 'agora'
  if (m < 60) return `${m}m`
  if (m < 1440) return `${Math.floor(m / 60)}h`
  return `${Math.floor(m / 1440)}d`
}

const QUICK_REPLIES = [
  'Sim, está disponível!',
  'Enviamos em 1-2 dias úteis.',
  'Aceitamos Multicaixa Express.',
  'Posso enviar mais fotos.',
  'Temos stock disponível.',
  'Obrigado pelo seu interesse!',
]

function ConvRow({ conv, onSelect }) {
  const unread = conv.unread_count || 0
  const last = conv.last_message
  const other = conv.other_participant || {}

  return (
    <button onClick={() => onSelect(conv)}
      style={{ display: 'flex', gap: 12, padding: '14px 16px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', borderBottom: '1px solid #1A1A1A', width: '100%' }}>
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <div style={{ width: 46, height: 46, borderRadius: '50%', background: '#6366f1', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
          {other.avatar_url
            ? <img src={other.avatar_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            : <span style={{ ...S, fontSize: 18, fontWeight: 700, color: '#FFF' }}>{(other.username || other.email || '?')[0].toUpperCase()}</span>
          }
        </div>
        {other.is_online && <div style={{ position: 'absolute', bottom: 1, right: 1, width: 10, height: 10, borderRadius: '50%', background: '#059669', border: '2px solid #0F0F0F' }} />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span style={{ ...S, fontSize: 14, fontWeight: unread > 0 ? 700 : 500, color: '#FFF' }}>
            {other.username || other.email?.split('@')[0] || 'Comprador'}
          </span>
          <span style={{ ...S, fontSize: 11, color: unread > 0 ? '#C9A84C' : '#555' }}>{timeAgo(last?.created_at)}</span>
        </div>
        {conv.product_context?.name && (
          <p style={{ ...S, fontSize: 11, color: '#C9A84C', marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{conv.product_context.name}</p>
        )}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <span style={{ ...S, fontSize: 13, color: '#9A9A9A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
            {last?.content || 'Sem mensagens'}
          </span>
          {unread > 0 && (
            <div style={{ width: 18, height: 18, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <span style={{ ...S, fontSize: 10, fontWeight: 700, color: '#0A0A0A' }}>{unread > 9 ? '9+' : unread}</span>
            </div>
          )}
        </div>
      </div>
    </button>
  )
}

function SkeletonRow() {
  return (
    <div style={{ display: 'flex', gap: 12, padding: '14px 16px', borderBottom: '1px solid #1A1A1A' }}>
      <div className="skeleton" style={{ width: 46, height: 46, borderRadius: '50%', flexShrink: 0 }} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 7, justifyContent: 'center' }}>
        <div className="skeleton" style={{ height: 13, width: '50%', borderRadius: 5 }} />
        <div className="skeleton" style={{ height: 11, width: '80%', borderRadius: 5 }} />
      </div>
    </div>
  )
}

function ConversationView({ conv, onBack }) {
  const other = conv.other_participant || {}
  const { messages, send, typingUsers } = useChatWS(conv.id)
  const [input, setInput] = useState('')
  const bottomRef = useRef(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages.length])

  const handleSend = (text) => {
    if (!text.trim()) return
    send(text)
    setInput('')
  }

  return (
    <SellerLayout title={other.username || other.email?.split('@')[0] || 'Comprador'} showBack>
      <div style={{ padding: '8px 16px', background: '#0F0F0F', borderBottom: '1px solid #1A1A1A', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
          </button>
          <div style={{ width: 36, height: 36, borderRadius: '50%', background: '#6366f1', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', flexShrink: 0 }}>
            {other.avatar_url
              ? <img src={other.avatar_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              : <span style={{ ...S, fontSize: 14, fontWeight: 700, color: '#FFF' }}>{(other.username || '?')[0].toUpperCase()}</span>
            }
          </div>
          <div>
            <p style={{ ...S, fontSize: 14, fontWeight: 600, color: '#FFF' }}>{other.username || other.email?.split('@')[0]}</p>
            {typingUsers.size > 0
              ? <p style={{ ...S, fontSize: 11, color: '#C9A84C' }}>A escrever…</p>
              : <p style={{ ...S, fontSize: 11, color: other.is_online ? '#059669' : '#9A9A9A' }}>{other.is_online ? 'Online' : 'Offline'}</p>
            }
          </div>
        </div>
      </div>

      <div className="screen" style={{ flex: 1, padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {messages.map(msg => (
          <div key={msg.id} style={{ display: 'flex', justifyContent: msg.is_mine ? 'flex-end' : 'flex-start' }}>
            <div style={{ maxWidth: '75%' }}>
              <div style={{ padding: '10px 14px', borderRadius: msg.is_mine ? '18px 18px 4px 18px' : '18px 18px 18px 4px', background: msg.is_mine ? '#C9A84C' : '#1A1A1A', border: !msg.is_mine ? '1px solid #2A2A2A' : 'none' }}>
                <p style={{ ...S, fontSize: 13, color: msg.is_mine ? '#0A0A0A' : '#FFF', lineHeight: 1.5 }}>{msg.content}</p>
              </div>
              <p style={{ ...S, fontSize: 10, color: '#555', marginTop: 3, textAlign: msg.is_mine ? 'right' : 'left' }}>
                {new Date(msg.created_at || Date.now()).toLocaleTimeString('pt-AO', { hour: '2-digit', minute: '2-digit' })}
              </p>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div style={{ padding: '6px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', scrollbarWidth: 'none', paddingBottom: 8 }}>
          {QUICK_REPLIES.map(r => (
            <button key={r} onClick={() => handleSend(r)}
              style={{ padding: '6px 12px', borderRadius: 50, flexShrink: 0, border: '1px solid #2A2A2A', background: '#141414', ...S, fontSize: 11, color: '#9A9A9A', cursor: 'pointer', whiteSpace: 'nowrap' }}>
              {r}
            </button>
          ))}
        </div>
      </div>

      <div style={{ padding: '8px 16px', background: '#0F0F0F', borderTop: '1px solid #1A1A1A', paddingBottom: 'max(20px, env(safe-area-inset-bottom))', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
          <div style={{ flex: 1, background: '#1A1A1A', border: '1px solid #2A2A2A', borderRadius: 20, padding: '10px 14px' }}>
            <textarea value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(input) } }}
              placeholder="Responder..." rows={1}
              style={{ width: '100%', background: 'none', border: 'none', outline: 'none', ...S, fontSize: 13, color: '#FFF', resize: 'none', lineHeight: 1.5 }} />
          </div>
          <button onClick={() => handleSend(input)} disabled={!input.trim()}
            style={{ width: 40, height: 40, borderRadius: 12, background: input.trim() ? '#C9A84C' : '#1A1A1A', border: input.trim() ? 'none' : '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: input.trim() ? 'pointer' : 'default', flexShrink: 0 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={input.trim() ? '#0A0A0A' : '#555'} strokeWidth="2.5" strokeLinecap="round"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
          </button>
        </div>
      </div>
    </SellerLayout>
  )
}

export default function SellerChatPage() {
  const [conversations, setConversations] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    chatApi.listConversations()
      .then(r => setConversations(r.data.results || r.data || []))
      .catch(() => setConversations([]))
      .finally(() => setLoading(false))
  }, [])

  const totalUnread = conversations.reduce((a, c) => a + (c.unread_count || 0), 0)

  if (selected) {
    return <ConversationView conv={selected} onBack={() => setSelected(null)} />
  }

  return (
    <SellerLayout title="Mensagens">
      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        {totalUnread > 0 && (
          <div style={{ background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.2)', borderRadius: 10, padding: '8px 12px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#C9A84C' }} />
            <span style={{ ...S, fontSize: 12, color: '#C9A84C' }}>
              {totalUnread} mensagem{totalUnread !== 1 ? 's' : ''} não lida{totalUnread !== 1 ? 's' : ''} de compradores
            </span>
          </div>
        )}
      </div>

      <div className="screen" style={{ flex: 1 }}>
        {loading ? (
          Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
        ) : conversations.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 32px', gap: 12, textAlign: 'center' }}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#2A2A2A" strokeWidth="1.5" strokeLinecap="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
            <p style={{ ...S, fontSize: 14, color: '#9A9A9A' }}>Ainda sem mensagens de compradores.</p>
          </div>
        ) : (
          conversations.map(conv => <ConvRow key={conv.id} conv={conv} onSelect={setSelected} />)
        )}
      </div>
    </SellerLayout>
  )
}
