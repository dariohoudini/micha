import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import { formatPrice } from '@/components/buyer/mockData'

const SELLER_CONVERSATIONS = [
  { id: 'sc-1', buyer: 'João Silva', avatar: 'J', lastMessage: 'Tem em tamanho M?', lastTime: '14:32', unread: 1, product: 'Vestido Capulana Premium', online: true, urgent: false },
  { id: 'sc-2', buyer: 'Maria Santos', avatar: 'M', lastMessage: 'Obrigada, vou encomendar!', lastTime: '11:15', unread: 0, product: 'Colar de Missangas', online: false, urgent: false },
  { id: 'sc-3', buyer: 'Pedro Neto', avatar: 'P', lastMessage: 'Qual o prazo de envio para Benguela?', lastTime: '09:40', unread: 2, product: 'Bolsa de Couro', online: true, urgent: true },
  { id: 'sc-4', buyer: 'Ana Costa', avatar: 'A', lastMessage: 'Pode fazer desconto se comprar 3?', lastTime: 'Ontem', unread: 0, product: 'Vestido Capulana Premium', online: false, urgent: false },
  { id: 'sc-5', buyer: 'Carlos Mendes', avatar: 'C', lastMessage: 'Aceita Multicaixa Express?', lastTime: 'Ontem', unread: 0, product: 'Bolsa de Couro', online: false, urgent: false },
]

const QUICK_REPLIES_SELLER = [
  'Sim, está disponível!',
  'Enviamos em 1-2 dias úteis.',
  'Aceitamos Multicaixa Express.',
  'Posso enviar mais fotos.',
  'Temos stock disponível.',
  'Obrigado pelo seu interesse!',
]

export default function SellerChatPage() {
  const navigate = useNavigate()
  const [conversations, setConversations] = useState(SELLER_CONVERSATIONS)
  const [selected, setSelected] = useState(null)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState({
    'sc-1': [
      { id: '1', content: 'Olá! Tem o Vestido Capulana em tamanho M?', sender: 'buyer', time: '14:30' },
      { id: '2', content: 'Bom dia João! Sim, temos em M e L.', sender: 'me', time: '14:31' },
      { id: '3', content: 'Tem em tamanho M?', sender: 'buyer', time: '14:32' },
    ],
    'sc-3': [
      { id: '4', content: 'Qual o prazo de envio para Benguela?', sender: 'buyer', time: '09:38' },
      { id: '5', content: 'Bom dia! Temos entregas para Benguela.', sender: 'me', time: '09:40' },
      { id: '6', content: 'Qual o prazo de envio para Benguela?', sender: 'buyer', time: '09:40' },
    ],
  })

  const sendReply = (text) => {
    if (!text.trim() || !selected) return
    const newMsg = { id: Date.now().toString(), content: text, sender: 'me', time: new Date().toLocaleTimeString('pt-AO', { hour: '2-digit', minute: '2-digit' }) }
    setMessages(prev => ({ ...prev, [selected.id]: [...(prev[selected.id] || []), newMsg] }))
    setConversations(prev => prev.map(c => c.id === selected.id ? { ...c, lastMessage: text, unread: 0 } : c))
    setInput('')
  }

  const totalUnread = conversations.reduce((a, c) => a + c.unread, 0)

  if (selected) {
    const convMessages = messages[selected.id] || []
    return (
      <SellerLayout title={selected.buyer} showBack>
        {/* Buyer info bar */}
        <div style={{ padding: '8px 16px 8px', background: '#0F0F0F', borderBottom: '1px solid #1A1A1A', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 12H5M12 5l-7 7 7 7" />
              </svg>
            </button>
            <div style={{ width: 36, height: 36, borderRadius: '50%', background: '#6366f1', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: '#FFFFFF' }}>{selected.avatar}</span>
            </div>
            <div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600, color: '#FFFFFF' }}>{selected.buyer}</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: selected.online ? '#059669' : '#9A9A9A' }}>
                {selected.online ? 'Online agora' : 'Offline'} · {selected.product}
              </p>
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="screen" style={{ flex: 1, padding: '16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {convMessages.map(msg => (
            <div key={msg.id} style={{ display: 'flex', justifyContent: msg.sender === 'me' ? 'flex-end' : 'flex-start' }}>
              <div style={{ maxWidth: '75%' }}>
                <div style={{ padding: '10px 14px', borderRadius: msg.sender === 'me' ? '18px 18px 4px 18px' : '18px 18px 18px 4px', background: msg.sender === 'me' ? '#C9A84C' : '#1A1A1A', border: msg.sender !== 'me' ? '1px solid #2A2A2A' : 'none' }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: msg.sender === 'me' ? '#0A0A0A' : '#FFFFFF', lineHeight: 1.5 }}>{msg.content}</p>
                </div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#555', marginTop: 3, textAlign: msg.sender === 'me' ? 'right' : 'left' }}>{msg.time}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Quick replies */}
        <div style={{ padding: '6px 16px 0', flexShrink: 0 }}>
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', scrollbarWidth: 'none', paddingBottom: 8 }}>
            {QUICK_REPLIES_SELLER.map(reply => (
              <button key={reply} onClick={() => sendReply(reply)}
                style={{ padding: '6px 12px', borderRadius: 50, flexShrink: 0, border: '1px solid #2A2A2A', background: '#141414', fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                {reply}
              </button>
            ))}
          </div>
        </div>

        {/* Input */}
        <div style={{ padding: '8px 16px', background: '#0F0F0F', borderTop: '1px solid #1A1A1A', paddingBottom: 'max(20px, env(safe-area-inset-bottom))', flexShrink: 0 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
            <div style={{ flex: 1, background: '#1A1A1A', border: '1px solid #2A2A2A', borderRadius: 20, padding: '10px 14px' }}>
              <textarea value={input} onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendReply(input) } }}
                placeholder="Responder..." rows={1}
                style={{ width: '100%', background: 'none', border: 'none', outline: 'none', fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', resize: 'none', lineHeight: 1.5 }} />
            </div>
            <button onClick={() => sendReply(input)} disabled={!input.trim()}
              style={{ width: 40, height: 40, borderRadius: 12, background: input.trim() ? '#C9A84C' : '#1A1A1A', border: input.trim() ? 'none' : '1px solid #2A2A2A', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: input.trim() ? 'pointer' : 'default', transition: 'background 0.2s', flexShrink: 0 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={input.trim() ? '#0A0A0A' : '#555'} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
        </div>
      </SellerLayout>
    )
  }

  return (
    <SellerLayout title="Mensagens">
      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        {totalUnread > 0 && (
          <div style={{ background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.2)', borderRadius: 10, padding: '8px 12px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#C9A84C' }} />
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C' }}>
              {totalUnread} mensagem{totalUnread !== 1 ? 's' : ''} não lida{totalUnread !== 1 ? 's' : ''} de compradores
            </span>
          </div>
        )}
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {conversations.map(conv => (
            <button key={conv.id} onClick={() => { setSelected(conv); setConversations(prev => prev.map(c => c.id === conv.id ? { ...c, unread: 0 } : c)) }}
              style={{ display: 'flex', gap: 12, padding: '14px 16px', background: conv.urgent ? 'rgba(245,158,11,0.04)' : 'none', border: 'none', cursor: 'pointer', textAlign: 'left', borderBottom: '1px solid #1A1A1A', borderLeft: conv.urgent ? '3px solid #f59e0b' : '3px solid transparent' }}>
              <div style={{ position: 'relative', flexShrink: 0 }}>
                <div style={{ width: 46, height: 46, borderRadius: '50%', background: '#6366f1', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <span style={{ fontSize: 18, fontWeight: 700, color: '#FFFFFF' }}>{conv.avatar}</span>
                </div>
                {conv.online && <div style={{ position: 'absolute', bottom: 1, right: 1, width: 10, height: 10, borderRadius: '50%', background: '#059669', border: '2px solid #0F0F0F' }} />}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: conv.unread > 0 ? 700 : 500, color: '#FFFFFF' }}>{conv.buyer}</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: conv.unread > 0 ? '#C9A84C' : '#555' }}>{conv.lastTime}</span>
                </div>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#C9A84C', marginBottom: 3 }}>{conv.product}</p>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{conv.lastMessage}</span>
                  {conv.unread > 0 && <div style={{ width: 18, height: 18, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginLeft: 8 }}>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, fontWeight: 700, color: '#0A0A0A' }}>{conv.unread}</span>
                  </div>}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </SellerLayout>
  )
}
