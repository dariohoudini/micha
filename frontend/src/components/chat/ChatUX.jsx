/**
 * MICHA Express — Chat UX Improvements
 * Covers: 50 (Typing indicator), 51 (Read receipts), 52 (Product card in chat),
 * 53 (Unread badge on nav), 54 (Quick reply chips)
 */
import { useState, useRef, useEffect } from 'react'

const GOLD = '#C9A84C'
const BG = '#0A0A0A'
const CARD = '#1E1E1E'
const BORDER = '#2A2A2A'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'

const QUICK_REPLIES = [
  'Obrigado pelo seu pedido!',
  'O produto está disponível.',
  'Entrega em 2-4 horas em Luanda.',
  'Pode pagar por Multicaixa.',
  'Vou verificar o stock.',
  'Sim, temos em stock!',
]


const fmt = (n) => n.toLocaleString('pt-AO') + ' Kz'

// ─── Read Receipt Ticks ──────────────────────────────────────────────────────
function ReadTicks({ status }) {
  const color = status === 'read' ? GOLD : MUTED
  return (
    <svg width="16" height="10" viewBox="0 0 16 10" fill="none">
      <polyline points="1 5 4 8 9 2" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      {(status === 'delivered' || status === 'read') && (
        <polyline points="6 5 9 8 14 2" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  )
}

// ─── Typing Indicator ────────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px' }}>
      <div style={{ width: 28, height: 28, borderRadius: '50%', background: CARD, border: `1px solid ${BORDER}`, flexShrink: 0 }} />
      <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: '16px 16px 16px 4px', padding: '10px 14px', display: 'flex', gap: 4, alignItems: 'center' }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{
            width: 6, height: 6, borderRadius: '50%', background: MUTED,
            animation: `bounce 1.2s ease infinite`,
            animationDelay: `${i * 0.2}s`
          }} />
        ))}
        <style>{`@keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-4px)}}`}</style>
      </div>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED }}>A escrever...</span>
    </div>
  )
}

// ─── Product Card in Chat ────────────────────────────────────────────────────
function ProductChatCard({ product, isMine }) {
  return (
    <div style={{
      maxWidth: 240, background: CARD, border: `1.5px solid ${isMine ? 'rgba(201,168,76,0.3)' : BORDER}`,
      borderRadius: isMine ? '16px 4px 16px 16px' : '4px 16px 16px 16px', overflow: 'hidden', cursor: 'pointer'
    }}>
      <div style={{ height: 100, background: product.image_color, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" strokeLinecap="round">
          <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
        </svg>
      </div>
      <div style={{ padding: '10px 12px' }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: TEXT, margin: '0 0 2px', lineHeight: 1.3 }}>{product.title}</p>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: MUTED, margin: '0 0 6px' }}>{product.store}</p>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 14, fontWeight: 700, color: GOLD }}>{fmt(product.price)}</span>
          <span style={{
            fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 600,
            color: product.in_stock ? '#059669' : '#EF4444',
            background: product.in_stock ? 'rgba(5,150,105,0.1)' : 'rgba(239,68,68,0.1)',
            padding: '2px 6px', borderRadius: 4
          }}>{product.in_stock ? 'Em stock' : 'Esgotado'}</span>
        </div>
      </div>
      <div style={{ borderTop: `1px solid ${BORDER}`, padding: '8px 12px' }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: GOLD, margin: 0, textAlign: 'center' }}>Ver produto →</p>
      </div>
    </div>
  )
}

// ─── Message Bubble ──────────────────────────────────────────────────────────
function MessageBubble({ msg }) {
  const isMine = msg.sender === 'me'
  return (
    <div style={{ display: 'flex', justifyContent: isMine ? 'flex-end' : 'flex-start', padding: '4px 16px' }}>
      <div style={{ maxWidth: '75%' }}>
        {msg.type === 'product' ? (
          <ProductChatCard product={msg.product} isMine={isMine} />
        ) : (
          <div style={{
            background: isMine ? 'rgba(201,168,76,0.15)' : CARD,
            border: `1px solid ${isMine ? 'rgba(201,168,76,0.25)' : BORDER}`,
            borderRadius: isMine ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
            padding: '10px 14px'
          }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: TEXT, margin: 0, lineHeight: 1.5 }}>{msg.text}</p>
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: isMine ? 'flex-end' : 'flex-start', marginTop: 4 }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: MUTED }}>{msg.time}</span>
          {isMine && <ReadTicks status={msg.status} />}
        </div>
      </div>
    </div>
  )
}

// ─── Unread Badge ────────────────────────────────────────────────────────────
export function UnreadBadge({ count }) {
  if (!count) return null
  return (
    <div style={{
      position: 'absolute', top: -4, right: -4, minWidth: 18, height: 18,
      borderRadius: 9, background: '#EF4444', border: `2px solid ${BG}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 4px'
    }}>
      <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 700, color: TEXT }}>
        {count > 99 ? '99+' : count}
      </span>
    </div>
  )
}

// ─── Full Chat UI ────────────────────────────────────────────────────────────
export default function ChatUI() {
  const [messages, setMessages] = useState([
    { id: 1, sender: 'them', text: 'Olá! Ainda tem o Samsung S24 disponível?', time: '14:20', status: 'read', type: 'text' },
    { id: 2, sender: 'me', text: 'Sim, temos em stock! Entregamos hoje em Luanda.', time: '14:21', status: 'read', type: 'text' },
    { id: 3, sender: 'me', product: null, time: '14:21', status: 'delivered', type: 'product' },
    { id: 4, sender: 'them', text: 'Perfeito! Qual o prazo de entrega?', time: '14:22', status: 'read', type: 'text' },
  ])
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [showQuickReplies, setShowQuickReplies] = useState(true)
  const [isSeller] = useState(true)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  const send = (text) => {
    if (!text.trim()) return
    const newMsg = { id: Date.now(), sender: 'me', text, time: new Date().toLocaleTimeString('pt-AO', { hour: '2-digit', minute: '2-digit' }), status: 'sent', type: 'text' }
    setMessages(prev => [...prev, newMsg])
    setInput('')
    setShowQuickReplies(false)

    // Simulate other party typing
    setTimeout(() => setIsTyping(true), 1000)
    setTimeout(() => {
      setIsTyping(false)
      setMessages(prev => [...prev, {
        id: Date.now() + 1, sender: 'them',
        text: 'Obrigado pela informação!', time: new Date().toLocaleTimeString('pt-AO', { hour: '2-digit', minute: '2-digit' }),
        status: 'delivered', type: 'text'
      }])
    }, 3000)
  }

  return (
    <div style={{ background: BG, height: '100vh', display: 'flex', flexDirection: 'column', maxWidth: 420, margin: '0 auto' }}>

      {/* Header */}
      <div style={{ padding: '50px 16px 12px', background: CARD, borderBottom: `1px solid ${BORDER}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 40, height: 40, borderRadius: '50%', background: '#1a1a40', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: TEXT }}>A</span>
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: TEXT, margin: 0 }}>Ana Rodrigues</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#059669', margin: 0 }}>Online agora</p>
          </div>
          <div style={{ position: 'relative' }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={MUTED} strokeWidth="1.5" strokeLinecap="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <UnreadBadge count={3} />
          </div>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 0' }}>
        {messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}
        {isTyping && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Quick replies for seller */}
      {isSeller && showQuickReplies && (
        <div style={{ padding: '8px 16px', flexShrink: 0 }}>
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4 }}>
            {QUICK_REPLIES.map((reply, i) => (
              <button key={i} onClick={() => send(reply)} style={{
                padding: '7px 12px', borderRadius: 20, border: `1px solid ${BORDER}`,
                background: CARD, color: TEXT, fontFamily: "'DM Sans', sans-serif",
                fontSize: 12, cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0,
                transition: 'all 0.15s'
              }}>
                {reply}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div style={{ padding: '8px 16px 24px', background: CARD, borderTop: `1px solid ${BORDER}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
          {/* Share product button */}
          <button onClick={() => {
            setMessages(prev => [...prev, { id: Date.now(), sender: 'me', product: null, time: new Date().toLocaleTimeString('pt-AO', { hour: '2-digit', minute: '2-digit' }), status: 'sent', type: 'product' }])
          }} style={{
            width: 40, height: 40, borderRadius: 12, border: `1px solid ${BORDER}`,
            background: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
          }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={MUTED} strokeWidth="1.5" strokeLinecap="round">
              <rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
            </svg>
          </button>

          <div style={{ flex: 1, background: BG, border: `1px solid ${BORDER}`, borderRadius: 20, padding: '10px 14px', display: 'flex', alignItems: 'center' }}>
            <input
              value={input}
              onChange={e => { setInput(e.target.value); setShowQuickReplies(false) }}
              onKeyDown={e => e.key === 'Enter' && send(input)}
              placeholder="Escreva uma mensagem..."
              style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: TEXT, fontFamily: "'DM Sans', sans-serif", fontSize: 14 }}
            />
          </div>

          <button onClick={() => send(input)} style={{
            width: 40, height: 40, borderRadius: '50%', border: 'none', cursor: 'pointer',
            background: input.trim() ? GOLD : BORDER,
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            transition: 'background 0.2s'
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={input.trim() ? '#000' : MUTED} strokeWidth="2" strokeLinecap="round">
              <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}
