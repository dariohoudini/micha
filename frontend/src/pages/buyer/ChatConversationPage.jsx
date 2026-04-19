import { useState, useRef, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useChat, MOCK_CONVERSATIONS, MOCK_MESSAGES, formatMessageTime } from '@/components/chat/useChat'
import { formatPrice } from '@/components/buyer/mockData'

const QUICK_REPLIES = [
  'Ainda está disponível?',
  'Qual o prazo de entrega?',
  'Tem outros tamanhos?',
  'Aceita Multicaixa?',
  'Pode fazer desconto?',
]

export default function ChatConversationPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const conv = MOCK_CONVERSATIONS.find(c => c.id === id) || MOCK_CONVERSATIONS[0]
  const { messages, setMessages, sendMessage, sendTyping, connected, typing } = useChat(id)
  const [input, setInput] = useState('')
  const [showQuickReplies, setShowQuickReplies] = useState(false)
  const [showAttach, setShowAttach] = useState(false)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  // Load mock messages
  useEffect(() => {
    setMessages(MOCK_MESSAGES[id] || MOCK_MESSAGES['conv-1'])
  }, [id])

  // Scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, typing])

  // Simulate seller reply
  const simulateReply = (userMsg) => {
    setTimeout(() => {
      const replies = [
        'Sim, claro! Posso ajudá-lo com isso.',
        'Obrigado pela sua mensagem! Vou verificar e responder brevemente.',
        'Boa pergunta! O produto está disponível sim.',
        'Perfeito! O prazo de entrega é de 1-2 dias em Luanda.',
        'Sim, aceitamos Multicaixa Express.',
      ]
      const reply = {
        id: Date.now().toString(),
        content: replies[Math.floor(Math.random() * replies.length)],
        sender: 'other',
        timestamp: new Date(),
        status: 'sent',
        type: 'text',
      }
      setMessages(prev => [...prev, reply])
    }, 1500)
  }

  const handleSend = () => {
    if (!input.trim()) return
    const msg = sendMessage(input.trim())
    simulateReply(msg)
    setInput('')
    setShowQuickReplies(false)
    setShowAttach(false)
  }

  const handleQuickReply = (text) => {
    const msg = sendMessage(text)
    simulateReply(msg)
    setShowQuickReplies(false)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const StatusIcon = ({ status }) => {
    if (status === 'sending') return <span style={{ fontSize: 10, color: '#9A9A9A' }}>⏳</span>
    if (status === 'sent') return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
    if (status === 'delivered') return (
      <div style={{ display: 'flex' }}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginLeft: -6 }}><polyline points="20 6 9 17 4 12" /></svg>
      </div>
    )
    if (status === 'seen') return (
      <div style={{ display: 'flex' }}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginLeft: -6 }}><polyline points="20 6 9 17 4 12" /></svg>
      </div>
    )
    return null
  }

  const MessageBubble = ({ msg }) => {
    const isMe = msg.sender === 'me'

    if (msg.type === 'product') {
      return (
        <div style={{ display: 'flex', justifyContent: isMe ? 'flex-end' : 'flex-start', marginBottom: 4 }}>
          <div style={{ maxWidth: '75%', background: isMe ? 'rgba(201,168,76,0.15)' : '#1E1E1E', borderRadius: isMe ? '18px 18px 4px 18px' : '18px 18px 18px 4px', border: `1px solid ${isMe ? 'rgba(201,168,76,0.3)' : '#2A2A2A'}`, overflow: 'hidden' }}>
            <div style={{ width: '100%', height: 100, background: msg.product?.image_color || '#1E1E1E', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
            <div style={{ padding: '10px 12px' }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF', marginBottom: 4 }}>{msg.product?.name}</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700, color: '#C9A84C', marginBottom: 8 }}>{formatPrice(msg.product?.price || 0)}</p>
              <button onClick={() => navigate(`/product/${msg.product?.id}`)}
                style={{ width: '100%', padding: '8px 0', borderRadius: 10, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
                Ver produto
              </button>
            </div>
          </div>
        </div>
      )
    }

    return (
      <div style={{ display: 'flex', justifyContent: isMe ? 'flex-end' : 'flex-start', marginBottom: 4, gap: 8, alignItems: 'flex-end' }}>
        {!isMe && (
          <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'linear-gradient(135deg, #C9A84C, #A67C35)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginBottom: 2 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: '#0A0A0A' }}>{conv.participant.avatar}</span>
          </div>
        )}
        <div style={{ maxWidth: '75%' }}>
          <div style={{
            padding: '10px 14px',
            borderRadius: isMe ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
            background: isMe ? '#C9A84C' : '#1E1E1E',
            border: isMe ? 'none' : '1px solid #2A2A2A',
          }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: isMe ? '#0A0A0A' : '#FFFFFF', lineHeight: 1.5, margin: 0 }}>
              {msg.content}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 3, justifyContent: isMe ? 'flex-end' : 'flex-start', paddingRight: isMe ? 2 : 0, paddingLeft: isMe ? 0 : 2 }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A' }}>
              {formatMessageTime(msg.timestamp)}
            </span>
            {isMe && <StatusIcon status={msg.status} />}
          </div>
        </div>
      </div>
    )
  }

  // Group messages by date
  const groupedMessages = messages.reduce((groups, msg) => {
    const date = new Date(msg.timestamp).toDateString()
    if (!groups[date]) groups[date] = []
    groups[date].push(msg)
    return groups
  }, {})

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0A0A0A' }}>
      {/* Header */}
      <div style={{ padding: '52px 16px 12px', background: '#0A0A0A', borderBottom: '1px solid #1E1E1E', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={() => navigate('/chat')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, flexShrink: 0 }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
          </button>

          {/* Seller info */}
          <div style={{ position: 'relative', flexShrink: 0 }}>
            <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'linear-gradient(135deg, #C9A84C, #A67C35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ fontSize: 16, fontWeight: 700, color: '#0A0A0A' }}>{conv.participant.avatar}</span>
            </div>
            {conv.online && <div style={{ position: 'absolute', bottom: 1, right: 1, width: 10, height: 10, borderRadius: '50%', background: '#059669', border: '2px solid #0A0A0A' }} />}
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, fontWeight: 600, color: '#FFFFFF' }}>{conv.participant.name}</span>
              {conv.participant.verified && <svg width="13" height="13" viewBox="0 0 24 24" fill="#C9A84C"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
            </div>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: conv.online ? '#059669' : '#9A9A9A' }}>
              {conv.online ? 'Online agora' : 'Offline'}
            </span>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={{ width: 36, height: 36, borderRadius: 10, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /><circle cx="5" cy="12" r="1" />
              </svg>
            </button>
          </div>
        </div>

        {/* Product context bar */}
        {conv.product && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10, background: '#141414', borderRadius: 10, padding: '8px 12px', border: '1px solid #2A2A2A' }}>
            <div style={{ width: 28, height: 28, borderRadius: 6, background: conv.product.image_color, flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#FFFFFF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{conv.product.name}</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(conv.product.price)}</p>
            </div>
            <button onClick={() => navigate('/explore')}
              style={{ padding: '5px 10px', borderRadius: 8, border: 'none', background: '#C9A84C', fontFamily: "'DM Sans', sans-serif", fontSize: 11, fontWeight: 600, color: '#0A0A0A', cursor: 'pointer', flexShrink: 0 }}>
              Ver
            </button>
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="screen" style={{ flex: 1, padding: '16px' }}>
        {Object.entries(groupedMessages).map(([date, msgs]) => (
          <div key={date}>
            {/* Date separator */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '12px 0' }}>
              <div style={{ flex: 1, height: 1, background: '#1E1E1E' }} />
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', whiteSpace: 'nowrap' }}>
                {new Date(date).toLocaleDateString('pt-AO', { weekday: 'long', day: '2-digit', month: 'long' })}
              </span>
              <div style={{ flex: 1, height: 1, background: '#1E1E1E' }} />
            </div>

            {msgs.map(msg => <MessageBubble key={msg.id} msg={msg} />)}
          </div>
        ))}

        {/* Typing indicator */}
        {typing && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'linear-gradient(135deg, #C9A84C, #A67C35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#0A0A0A' }}>{conv.participant.avatar}</span>
            </div>
            <div style={{ background: '#1E1E1E', borderRadius: '18px 18px 18px 4px', padding: '10px 14px', border: '1px solid #2A2A2A' }}>
              <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                {[0, 1, 2].map(i => (
                  <div key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: '#9A9A9A', animation: `bounce 1.2s ${i * 0.2}s infinite` }} />
                ))}
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
        <style>{`@keyframes bounce { 0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-6px)} }`}</style>
      </div>

      {/* Quick replies */}
      {showQuickReplies && (
        <div style={{ padding: '8px 16px', background: '#0A0A0A', borderTop: '1px solid #1E1E1E' }}>
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', scrollbarWidth: 'none', paddingBottom: 4 }}>
            {QUICK_REPLIES.map(reply => (
              <button key={reply} onClick={() => handleQuickReply(reply)}
                style={{ padding: '7px 14px', borderRadius: 50, flexShrink: 0, border: '1px solid #2A2A2A', background: '#141414', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#FFFFFF', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                {reply}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input bar */}
      <div style={{ padding: '12px 16px', background: '#0A0A0A', borderTop: '1px solid #1E1E1E', paddingBottom: 'max(20px, env(safe-area-inset-bottom))', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
          {/* Attach button */}
          <button onClick={() => { setShowAttach(!showAttach); setShowQuickReplies(false) }}
            style={{ width: 40, height: 40, borderRadius: 12, background: '#1E1E1E', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>

          {/* Text input */}
          <div style={{ flex: 1, background: '#1E1E1E', border: '1px solid #2A2A2A', borderRadius: 20, padding: '10px 14px', display: 'flex', alignItems: 'flex-end', gap: 8 }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => { setInput(e.target.value); sendTyping() }}
              onKeyDown={handleKeyDown}
              placeholder="Mensagem..."
              rows={1}
              style={{
                flex: 1, background: 'none', border: 'none', outline: 'none',
                fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#FFFFFF',
                resize: 'none', maxHeight: 100, lineHeight: 1.5,
                scrollbarWidth: 'none',
              }}
            />
            {/* Quick replies toggle */}
            <button onClick={() => { setShowQuickReplies(!showQuickReplies); setShowAttach(false) }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, flexShrink: 0, opacity: 0.6 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01" />
              </svg>
            </button>
          </div>

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            style={{
              width: 40, height: 40, borderRadius: 12, flexShrink: 0,
              background: input.trim() ? '#C9A84C' : '#1E1E1E',
              border: input.trim() ? 'none' : '1px solid #2A2A2A',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: input.trim() ? 'pointer' : 'default',
              transition: 'background 0.2s',
            }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke={input.trim() ? '#0A0A0A' : '#9A9A9A'} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>

        {/* Attach options */}
        {showAttach && (
          <div style={{ display: 'flex', gap: 12, marginTop: 12, justifyContent: 'center' }}>
            {[
              { icon: 'M4 16l4.586-4.586a2 2 0 0 1 2.828 0L16 16m-2-2l1.586-1.586a2 2 0 0 1 2.828 0L20 14m-6-6h.01M6 20h12a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2z', label: 'Foto', color: '#8b5cf6' },
              { icon: 'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z', label: 'Produto', color: '#C9A84C' },
              { icon: 'M17.657 16.657L13.414 20.9a1.998 1.998 0 0 1-2.827 0l-4.244-4.243a8 8 0 1 1 11.314 0z M15 11a3 3 0 1 1-6 0 3 3 0 0 1 6 0z', label: 'Localização', color: '#10b981' },
            ].map(action => (
              <button key={action.label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer' }}>
                <div style={{ width: 48, height: 48, borderRadius: 14, background: '#141414', border: '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={action.color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d={action.icon} />
                  </svg>
                </div>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>{action.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
