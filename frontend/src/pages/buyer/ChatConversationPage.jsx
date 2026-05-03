import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useChatWS } from '@/hooks/useChatWS'
import { chatApi } from '@/api/chat'
import { useAuthStore } from '@/stores/authStore'

const QUICK_REPLIES = [
  'Ainda está disponível?', 'Qual o prazo de entrega?',
  'Tem outros tamanhos?', 'Aceita Multicaixa?', 'Pode fazer desconto?',
]

function fmt(n) { return Number(n || 0).toLocaleString('pt-AO') + ' Kz' }

function fmtTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('pt-AO', { hour: '2-digit', minute: '2-digit' })
}

function StatusTicks({ status }) {
  const gold = '#C9A84C', grey = '#9A9A9A'
  if (status === 'sending') return <span style={{ fontSize: 9, color: grey }}>⏳</span>
  if (status === 'sent') return (
    <svg width="14" height="9" viewBox="0 0 14 9" fill="none">
      <polyline points="1 4 4 7 9 1" stroke={grey} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
  if (status === 'delivered') return (
    <svg width="18" height="9" viewBox="0 0 18 9" fill="none">
      <polyline points="1 4 4 7 9 1" stroke={grey} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points="6 4 9 7 14 1" stroke={grey} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
  if (status === 'seen') return (
    <svg width="18" height="9" viewBox="0 0 18 9" fill="none">
      <polyline points="1 4 4 7 9 1" stroke={gold} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points="6 4 9 7 14 1" stroke={gold} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
  return null
}

export default function ChatConversationPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const myId = useAuthStore(s => s.user?.id)
  const { messages, setMessages, connected, typingUsers, onlineUsers, send, sendTyping, markRead } = useChatWS(id)
  const [input, setInput] = useState('')
  const [conv, setConv] = useState(null)
  const [loadingHistory, setLoadingHistory] = useState(true)
  const [showQuickReplies, setShowQuickReplies] = useState(false)
  const [showAttach, setShowAttach] = useState(false)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  // Load conversation info + message history
  useEffect(() => {
    Promise.all([
      chatApi.listConversations().catch(() => ({ data: [] })),
      chatApi.getMessages(id, { limit: 50 }).catch(() => ({ data: { results: [] } })),
    ]).then(([convRes, msgsRes]) => {
      const convList = convRes.data?.results || convRes.data || []
      setConv(convList.find(c => String(c.id) === String(id)) || null)
      const history = (msgsRes.data?.results || msgsRes.data || [])
        .reverse()
        .map(m => ({
          id: String(m.id),
          content: m.content,
          sender: String(m.sender) === String(myId) ? 'me' : m.sender,
          senderName: m.sender_name,
          timestamp: new Date(m.created_at),
          status: m.is_read ? 'seen' : 'delivered',
          type: m.message_type || 'text',
          product: m.product || null,
        }))
      setMessages(history)
    }).finally(() => setLoadingHistory(false))

    chatApi.markRead(id).catch(() => {})
  }, [id, myId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, typingUsers.size])

  // Mark incoming messages as read when visible
  useEffect(() => {
    const last = [...messages].reverse().find(m => m.sender !== 'me' && m.status !== 'seen')
    if (last) markRead(last.id)
  }, [messages])

  const handleSend = useCallback(() => {
    if (!input.trim()) return
    send(input.trim())
    setInput('')
    setShowQuickReplies(false)
    setShowAttach(false)
  }, [input, send])

  const other = conv?.participants?.find(p => String(p.id) !== String(myId)) || {}
  const initials = (other.full_name || other.username || '?').slice(0, 2).toUpperCase()
  const isOtherOnline = onlineUsers.has(other.id) || conv?.is_online
  const isTyping = typingUsers.size > 0

  const grouped = messages.reduce((g, msg) => {
    const key = new Date(msg.timestamp).toDateString()
    if (!g[key]) g[key] = []
    g[key].push(msg)
    return g
  }, {})

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      {/* Header */}
      <div style={{ padding: 'max(52px,env(safe-area-inset-top)) 16px 12px', background: '#0A0A0A', borderBottom: '1px solid #1E1E1E', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={() => navigate('/chat')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, flexShrink: 0 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 5l-7 7 7 7" /></svg>
          </button>

          <div style={{ position: 'relative', flexShrink: 0 }}>
            <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'linear-gradient(135deg,#C9A84C,#A67C35)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
              {other.avatar
                ? <img src={other.avatar} alt={initials} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                : <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 15, fontWeight: 700, color: '#0A0A0A' }}>{initials}</span>
              }
            </div>
            {isOtherOnline && <div style={{ position: 'absolute', bottom: 1, right: 1, width: 10, height: 10, borderRadius: '50%', background: '#059669', border: '2px solid #0A0A0A' }} />}
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 15, fontWeight: 600, color: '#FFF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {other.full_name || other.username || '…'}
              </span>
              {other.is_verified && (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="#C9A84C" aria-label="Verificado">
                  <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              )}
            </div>
            <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 12, color: isOtherOnline ? '#059669' : '#9A9A9A' }}>
              {isTyping ? 'a escrever…' : isOtherOnline ? 'Online agora' : 'Offline'}
            </span>
          </div>

          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {!connected && (
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#ef4444' }} title="Sem ligação" />
            )}
            <button style={{ width: 36, height: 36, borderRadius: 10, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /><circle cx="5" cy="12" r="1" /></svg>
            </button>
          </div>
        </div>

        {conv?.product && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10, background: '#141414', borderRadius: 10, padding: '8px 12px', border: '1px solid #2A2A2A' }}>
            <div style={{ width: 28, height: 28, borderRadius: 6, background: conv.product.image_color || '#1E1E1E', overflow: 'hidden', flexShrink: 0 }}>
              {conv.product.image_url && <img src={conv.product.image_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 12, color: '#FFF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{conv.product.name}</p>
              <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 12, fontWeight: 700, color: '#C9A84C' }}>{fmt(conv.product.price)}</p>
            </div>
            <button onClick={() => navigate(`/product/${conv.product.id}`)} style={{ padding: '5px 10px', borderRadius: 8, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans',sans-serif", fontSize: 11, fontWeight: 600, color: '#0A0A0A', cursor: 'pointer', flexShrink: 0 }}>Ver</button>
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="screen" style={{ flex: 1, padding: '12px 16px' }}>
        {loadingHistory ? (
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: i % 2 === 0 ? 'flex-end' : 'flex-start', marginBottom: 10 }}>
              <div className="skeleton" style={{ height: 40, width: `${45 + (i * 7) % 30}%`, borderRadius: 14 }} />
            </div>
          ))
        ) : (
          Object.entries(grouped).map(([date, msgs]) => (
            <div key={date}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '12px 0' }}>
                <div style={{ flex: 1, height: 1, background: '#1E1E1E' }} />
                <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 11, color: '#9A9A9A', whiteSpace: 'nowrap' }}>
                  {new Date(date).toLocaleDateString('pt-AO', { weekday: 'long', day: '2-digit', month: 'long' })}
                </span>
                <div style={{ flex: 1, height: 1, background: '#1E1E1E' }} />
              </div>
              {msgs.map(msg => {
                const isMe = msg.sender === 'me'
                if (msg.type === 'product' && msg.product) {
                  return (
                    <div key={msg.id} style={{ display: 'flex', justifyContent: isMe ? 'flex-end' : 'flex-start', marginBottom: 8 }}>
                      <div style={{ maxWidth: '72%', background: isMe ? 'rgba(201,168,76,0.15)' : '#1E1E1E', borderRadius: isMe ? '18px 18px 4px 18px' : '18px 18px 18px 4px', border: `1px solid ${isMe ? 'rgba(201,168,76,0.3)' : '#2A2A2A'}`, overflow: 'hidden' }}>
                        <div style={{ width: '100%', height: 90, background: msg.product.image_color || '#2A2A2A', overflow: 'hidden' }}>
                          {msg.product.image_url && <img src={msg.product.image_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
                        </div>
                        <div style={{ padding: '10px 12px' }}>
                          <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 13, fontWeight: 600, color: '#FFF', marginBottom: 4 }}>{msg.product.name}</p>
                          <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 14, fontWeight: 700, color: '#C9A84C', marginBottom: 8 }}>{fmt(msg.product.price)}</p>
                          <button onClick={() => navigate(`/product/${msg.product.id}`)} style={{ width: '100%', padding: '8px 0', borderRadius: 10, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans',sans-serif", fontSize: 12, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>Ver produto</button>
                        </div>
                      </div>
                    </div>
                  )
                }
                return (
                  <div key={msg.id} style={{ display: 'flex', justifyContent: isMe ? 'flex-end' : 'flex-start', marginBottom: 4, gap: 8, alignItems: 'flex-end' }}>
                    {!isMe && (
                      <div style={{ width: 26, height: 26, borderRadius: '50%', background: 'linear-gradient(135deg,#C9A84C,#A67C35)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginBottom: 2 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: '#0A0A0A' }}>{initials}</span>
                      </div>
                    )}
                    <div style={{ maxWidth: '75%' }}>
                      <div style={{ padding: '10px 14px', borderRadius: isMe ? '18px 18px 4px 18px' : '18px 18px 18px 4px', background: isMe ? '#C9A84C' : '#1E1E1E', border: isMe ? 'none' : '1px solid #2A2A2A' }}>
                        <p style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 14, color: isMe ? '#0A0A0A' : '#FFF', lineHeight: 1.5, margin: 0 }}>{msg.content}</p>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 3, justifyContent: isMe ? 'flex-end' : 'flex-start', padding: '0 2px' }}>
                        <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 10, color: '#9A9A9A' }}>{fmtTime(msg.timestamp)}</span>
                        {isMe && <StatusTicks status={msg.status} />}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ))
        )}

        {isTyping && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
            <div style={{ width: 26, height: 26, borderRadius: '50%', background: 'linear-gradient(135deg,#C9A84C,#A67C35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: '#0A0A0A' }}>{initials}</span>
            </div>
            <div style={{ background: '#1E1E1E', borderRadius: '18px 18px 18px 4px', padding: '10px 14px', border: '1px solid #2A2A2A' }}>
              <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                {[0, 1, 2].map(i => (
                  <div key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: '#9A9A9A', animation: `typingBounce 1.2s ${i * 0.2}s infinite` }} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
        <style>{`@keyframes typingBounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-5px)}}`}</style>
      </div>

      {/* Quick replies */}
      {showQuickReplies && (
        <div style={{ padding: '8px 16px', background: '#0A0A0A', borderTop: '1px solid #1E1E1E' }}>
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', scrollbarWidth: 'none', paddingBottom: 4 }}>
            {QUICK_REPLIES.map(r => (
              <button key={r} onClick={() => { send(r); setShowQuickReplies(false) }}
                style={{ padding: '7px 14px', borderRadius: 50, flexShrink: 0, border: '1px solid #2A2A2A', background: '#141414', fontFamily: "'DM Sans',sans-serif", fontSize: 12, color: '#FFF', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                {r}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input bar */}
      <div style={{ padding: '12px 16px', paddingBottom: 'max(20px,env(safe-area-inset-bottom))', background: '#0A0A0A', borderTop: '1px solid #1E1E1E', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
          <button onClick={() => { setShowAttach(!showAttach); setShowQuickReplies(false) }}
            style={{ width: 40, height: 40, borderRadius: 12, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg>
          </button>

          <div style={{ flex: 1, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 20, padding: '10px 14px', display: 'flex', alignItems: 'flex-end', gap: 8 }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => { setInput(e.target.value); sendTyping() }}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
              placeholder="Mensagem…"
              rows={1}
              style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontFamily: "'DM Sans',sans-serif", fontSize: 14, color: '#FFF', resize: 'none', maxHeight: 100, lineHeight: 1.5, scrollbarWidth: 'none' }}
            />
            <button onClick={() => { setShowQuickReplies(!showQuickReplies); setShowAttach(false) }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, flexShrink: 0, opacity: 0.6 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01" /></svg>
            </button>
          </div>

          <button onClick={handleSend} disabled={!input.trim()}
            style={{ width: 40, height: 40, borderRadius: 12, flexShrink: 0, background: input.trim() ? '#C9A84C' : '#1E1E1E', border: input.trim() ? 'none' : '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: input.trim() ? 'pointer' : 'default', transition: 'background 0.2s' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={input.trim() ? '#0A0A0A' : '#9A9A9A'} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>

        {showAttach && (
          <div style={{ display: 'flex', gap: 12, marginTop: 12, justifyContent: 'center' }}>
            {[
              { icon: 'M4 16l4.586-4.586a2 2 0 0 1 2.828 0L16 16m-2-2l1.586-1.586a2 2 0 0 1 2.828 0L20 14m-6-6h.01M6 20h12a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2z', label: 'Foto', color: '#8b5cf6' },
              { icon: 'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z', label: 'Produto', color: '#C9A84C' },
              { icon: 'M17.657 16.657L13.414 20.9a1.998 1.998 0 0 1-2.827 0l-4.244-4.243a8 8 0 1 1 11.314 0z M15 11a3 3 0 1 1-6 0 3 3 0 0 1 6 0z', label: 'Localização', color: '#10b981' },
            ].map(a => (
              <button key={a.label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer' }}>
                <div style={{ width: 48, height: 48, borderRadius: 14, background: '#141414', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={a.color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={a.icon} /></svg>
                </div>
                <span style={{ fontFamily: "'DM Sans',sans-serif", fontSize: 11, color: '#9A9A9A' }}>{a.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
