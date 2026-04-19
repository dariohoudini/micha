import { useState } from 'react'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'

const MOCK_CHATS = [
  {
    id: 'chat-1',
    buyer: 'João Silva',
    seller: 'Moda Luanda',
    buyerAvatar: 'J',
    sellerAvatar: 'M',
    lastMessage: 'Pode enviar fora da plataforma?',
    lastTime: '14:32',
    status: 'flagged',
    reports: 1,
    messages: [
      { id: '1', sender: 'buyer', content: 'Olá, tem o produto disponível?', time: '14:20' },
      { id: '2', sender: 'seller', content: 'Sim, temos em stock!', time: '14:21' },
      { id: '3', sender: 'buyer', content: 'Qual o preço se pagar fora da plataforma?', time: '14:30' },
      { id: '4', sender: 'seller', content: 'Posso fazer melhor preço por fora.', time: '14:31' },
      { id: '5', sender: 'buyer', content: 'Pode enviar fora da plataforma?', time: '14:32' },
    ],
  },
  {
    id: 'chat-2',
    buyer: 'Maria Santos',
    seller: 'TechShop Angola',
    buyerAvatar: 'M',
    sellerAvatar: 'T',
    lastMessage: 'Perfeito! Vou encomendar agora.',
    lastTime: '11:15',
    status: 'normal',
    reports: 0,
    messages: [
      { id: '6', sender: 'buyer', content: 'O Samsung A55 tem garantia?', time: '11:00' },
      { id: '7', sender: 'seller', content: 'Sim, 1 ano de garantia oficial.', time: '11:05' },
      { id: '8', sender: 'buyer', content: 'Perfeito! Vou encomendar agora.', time: '11:15' },
    ],
  },
  {
    id: 'chat-3',
    buyer: 'Pedro Neto',
    seller: 'Beauty Angola',
    buyerAvatar: 'P',
    sellerAvatar: 'B',
    lastMessage: 'Envia o número do Multicaixa por aqui.',
    lastTime: '09:40',
    status: 'flagged',
    reports: 2,
    messages: [
      { id: '9', sender: 'buyer', content: 'Quero comprar o kit skincare.', time: '09:30' },
      { id: '10', sender: 'seller', content: 'Ótimo! Temos disponível.', time: '09:32' },
      { id: '11', sender: 'buyer', content: 'Posso pagar directo para si?', time: '09:38' },
      { id: '12', sender: 'seller', content: 'Envia o número do Multicaixa por aqui.', time: '09:40' },
    ],
  },
  {
    id: 'chat-4',
    buyer: 'Ana Costa',
    seller: 'SportZone AO',
    buyerAvatar: 'A',
    sellerAvatar: 'S',
    lastMessage: 'Tem em tamanho 42?',
    lastTime: 'Ontem',
    status: 'normal',
    reports: 0,
    messages: [
      { id: '13', sender: 'buyer', content: 'Tem em tamanho 42?', time: 'Ontem 16:20' },
    ],
  },
]

const STATUS_CONFIG = {
  normal:  { label: 'Normal',    color: '#10b981', bg: 'rgba(16,185,129,0.1)' },
  flagged: { label: 'Sinalizado', color: '#ef4444', bg: 'rgba(239,68,68,0.1)' },
  blocked: { label: 'Bloqueado', color: '#6b7280', bg: 'rgba(107,114,128,0.1)' },
}

const FLAG_REASONS = [
  'Tentativa de pagamento fora da plataforma',
  'Conteúdo inapropriado',
  'Spam ou publicidade',
  'Produto proibido',
  'Fraude ou burla',
  'Assédio ou ameaças',
]

export default function AdminChatPage() {
  const [chats, setChats] = useState(MOCK_CHATS)
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const [showAction, setShowAction] = useState(false)
  const [adminNote, setAdminNote] = useState('')
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 2500)
  }

  const blockChat = (id) => {
    setChats(prev => prev.map(c => c.id === id ? { ...c, status: 'blocked' } : c))
    showToast('Conversa bloqueada. Utilizadores notificados.', 'error')
    setSelected(null)
    setShowAction(false)
  }

  const clearFlag = (id) => {
    setChats(prev => prev.map(c => c.id === id ? { ...c, status: 'normal', reports: 0 } : c))
    showToast('Sinalização removida. Conversa marcada como normal.')
    setSelected(null)
    setShowAction(false)
  }

  const warnUsers = (id) => {
    showToast('Aviso enviado a ambos os utilizadores.')
    setSelected(prev => prev ? { ...prev, warned: true } : null)
    setShowAction(false)
  }

  const filtered = chats.filter(c => {
    if (filter === 'flagged') return c.status === 'flagged'
    if (filter === 'blocked') return c.status === 'blocked'
    return true
  })

  const flaggedCount = chats.filter(c => c.status === 'flagged').length

  return (
    <AdminLayout title="Chat Moderação">
      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: toast.type === 'error' ? '#dc2626' : '#059669', color: '#FFFFFF', padding: '10px 20px', borderRadius: 12, fontSize: 13, fontWeight: 500, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap' }}>
          {toast.msg}
        </div>
      )}

      {/* Conversation viewer + action modal */}
      {selected && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', zIndex: 100, display: 'flex', flexDirection: 'column' }}
          onClick={e => { if (e.target === e.currentTarget) setSelected(null) }}>
          <div style={{ background: ADMIN_COLORS.card, flex: 1, display: 'flex', flexDirection: 'column', maxHeight: '90vh', marginTop: 'auto', borderRadius: '20px 20px 0 0', border: `1px solid ${ADMIN_COLORS.border}` }}>

            {/* Modal header */}
            <div style={{ padding: '16px 20px', borderBottom: `1px solid ${ADMIN_COLORS.border}`, flexShrink: 0 }}>
              <div style={{ width: 36, height: 4, borderRadius: 2, background: ADMIN_COLORS.border, margin: '0 auto 16px' }} />
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <h3 style={{ fontSize: 15, fontWeight: 700, color: ADMIN_COLORS.text }}>
                    {selected.buyer} ↔ {selected.seller}
                  </h3>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 600, color: STATUS_CONFIG[selected.status].color, background: STATUS_CONFIG[selected.status].bg, padding: '2px 8px', borderRadius: 20 }}>
                      {STATUS_CONFIG[selected.status].label}
                    </span>
                    {selected.reports > 0 && (
                      <span style={{ fontSize: 11, color: '#ef4444' }}>⚠️ {selected.reports} reporte(s)</span>
                    )}
                  </div>
                </div>
                <button onClick={() => setShowAction(!showAction)}
                  style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid rgba(99,102,241,0.3)', background: 'rgba(99,102,241,0.1)', fontSize: 12, color: '#818cf8', cursor: 'pointer' }}>
                  Acções
                </button>
              </div>
            </div>

            {/* Action panel */}
            {showAction && (
              <div style={{ padding: '12px 20px', background: ADMIN_COLORS.surface, borderBottom: `1px solid ${ADMIN_COLORS.border}`, flexShrink: 0 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <p style={{ fontSize: 11, color: ADMIN_COLORS.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Acções de moderação</p>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button onClick={() => warnUsers(selected.id)}
                      style={{ padding: '8px 14px', borderRadius: 10, border: '1px solid rgba(245,158,11,0.3)', background: 'rgba(245,158,11,0.1)', fontSize: 12, fontWeight: 500, color: '#f59e0b', cursor: 'pointer' }}>
                      ⚠️ Avisar ambos
                    </button>
                    {selected.status !== 'blocked' && (
                      <button onClick={() => blockChat(selected.id)}
                        style={{ padding: '8px 14px', borderRadius: 10, border: '1px solid rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.1)', fontSize: 12, fontWeight: 500, color: '#ef4444', cursor: 'pointer' }}>
                        🚫 Bloquear conversa
                      </button>
                    )}
                    {selected.status === 'flagged' && (
                      <button onClick={() => clearFlag(selected.id)}
                        style={{ padding: '8px 14px', borderRadius: 10, border: '1px solid rgba(16,185,129,0.3)', background: 'rgba(16,185,129,0.1)', fontSize: 12, fontWeight: 500, color: '#10b981', cursor: 'pointer' }}>
                        ✓ Limpar sinalização
                      </button>
                    )}
                  </div>

                  {/* Flag reason picker */}
                  {selected.status === 'normal' && (
                    <div>
                      <p style={{ fontSize: 11, color: ADMIN_COLORS.muted, marginBottom: 6 }}>Motivo da sinalização:</p>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {FLAG_REASONS.map(reason => (
                          <button key={reason}
                            style={{ padding: '4px 10px', borderRadius: 50, border: `1px solid ${ADMIN_COLORS.border}`, background: 'transparent', fontSize: 11, color: ADMIN_COLORS.muted, cursor: 'pointer' }}>
                            {reason}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Admin note */}
                  <textarea value={adminNote} onChange={e => setAdminNote(e.target.value)}
                    placeholder="Nota interna sobre esta conversa..."
                    style={{ background: ADMIN_COLORS.bg, border: `1px solid ${ADMIN_COLORS.border}`, borderRadius: 10, padding: '10px 12px', color: ADMIN_COLORS.text, fontSize: 12, resize: 'none', outline: 'none', fontFamily: "'DM Sans', sans-serif", lineHeight: 1.5 }}
                    rows={2} />
                </div>
              </div>
            )}

            {/* Messages */}
            <div className="screen" style={{ flex: 1, padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {/* Flagged warning */}
              {selected.status === 'flagged' && (
                <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 10, padding: '10px 14px', marginBottom: 4 }}>
                  <p style={{ fontSize: 12, color: '#ef4444', fontWeight: 600 }}>
                    ⚠️ Esta conversa foi sinalizada automaticamente por conteúdo suspeito.
                  </p>
                  <p style={{ fontSize: 11, color: ADMIN_COLORS.muted, marginTop: 4 }}>
                    Possível tentativa de pagamento fora da plataforma ou fraude.
                  </p>
                </div>
              )}

              {selected.messages.map((msg, i) => {
                const isBuyer = msg.sender === 'buyer'
                const isFlagged = selected.status === 'flagged' && i >= selected.messages.length - 2
                return (
                  <div key={msg.id}>
                    <div style={{ display: 'flex', justifyContent: isBuyer ? 'flex-start' : 'flex-end', gap: 8, alignItems: 'flex-end' }}>
                      {isBuyer && (
                        <div style={{ width: 24, height: 24, borderRadius: '50%', background: '#6366f1', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                          <span style={{ fontSize: 10, fontWeight: 700, color: '#FFFFFF' }}>{selected.buyerAvatar}</span>
                        </div>
                      )}
                      <div style={{ maxWidth: '70%' }}>
                        <div style={{ padding: '8px 12px', borderRadius: isBuyer ? '16px 16px 16px 4px' : '16px 16px 4px 16px', background: isBuyer ? ADMIN_COLORS.surface : 'rgba(99,102,241,0.15)', border: `1px solid ${isFlagged ? 'rgba(239,68,68,0.4)' : isBuyer ? ADMIN_COLORS.border : 'rgba(99,102,241,0.2)'}` }}>
                          <p style={{ fontSize: 13, color: isFlagged ? '#fca5a5' : ADMIN_COLORS.text, lineHeight: 1.4 }}>{msg.content}</p>
                        </div>
                        <div style={{ display: 'flex', gap: 6, marginTop: 3, justifyContent: isBuyer ? 'flex-start' : 'flex-end', alignItems: 'center' }}>
                          <span style={{ fontSize: 9, color: ADMIN_COLORS.muted }}>{isBuyer ? selected.buyer : selected.seller}</span>
                          <span style={{ fontSize: 9, color: ADMIN_COLORS.muted }}>·</span>
                          <span style={{ fontSize: 9, color: ADMIN_COLORS.muted }}>{msg.time}</span>
                          {isFlagged && <span style={{ fontSize: 9, color: '#ef4444', fontWeight: 600 }}>⚠️ Suspeito</span>}
                        </div>
                      </div>
                      {!isBuyer && (
                        <div style={{ width: 24, height: 24, borderRadius: '50%', background: '#C9A84C', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                          <span style={{ fontSize: 10, fontWeight: 700, color: '#0A0A0A' }}>{selected.sellerAvatar}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            <div style={{ padding: '12px 20px 40px', borderTop: `1px solid ${ADMIN_COLORS.border}`, flexShrink: 0 }}>
              <button onClick={() => setSelected(null)}
                style={{ width: '100%', padding: '12px', borderRadius: 12, border: `1px solid ${ADMIN_COLORS.border}`, background: 'transparent', fontSize: 14, color: ADMIN_COLORS.muted, cursor: 'pointer' }}>
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}

      <div style={{ padding: '12px 16px 0', flexShrink: 0 }}>
        {/* Stats */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {[
            { l: 'Total', v: chats.length, c: ADMIN_COLORS.text },
            { l: 'Sinalizadas', v: chats.filter(c => c.status === 'flagged').length, c: '#ef4444' },
            { l: 'Bloqueadas', v: chats.filter(c => c.status === 'blocked').length, c: '#6b7280' },
            { l: 'Normais', v: chats.filter(c => c.status === 'normal').length, c: '#10b981' },
          ].map(s => (
            <div key={s.l} style={{ flex: 1, background: ADMIN_COLORS.card, borderRadius: 10, border: `1px solid ${ADMIN_COLORS.border}`, padding: '8px 6px', textAlign: 'center' }}>
              <p style={{ fontSize: 16, fontWeight: 700, color: s.c }}>{s.v}</p>
              <p style={{ fontSize: 9, color: ADMIN_COLORS.muted, marginTop: 1 }}>{s.l}</p>
            </div>
          ))}
        </div>

        {/* Alert if flagged */}
        {flaggedCount > 0 && (
          <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 10, padding: '10px 14px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#ef4444', flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: '#ef4444', fontWeight: 500 }}>
              {flaggedCount} conversa{flaggedCount !== 1 ? 's' : ''} sinalizada{flaggedCount !== 1 ? 's' : ''} — revisão necessária
            </span>
          </div>
        )}

        {/* Filter tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {[{ v: 'all', l: 'Todas' }, { v: 'flagged', l: `Sinalizadas (${flaggedCount})` }, { v: 'blocked', l: 'Bloqueadas' }].map(f => (
            <button key={f.v} onClick={() => setFilter(f.v)}
              style={{ padding: '5px 14px', borderRadius: 50, flexShrink: 0, border: `1px solid ${filter === f.v ? '#6366f1' : ADMIN_COLORS.border}`, background: filter === f.v ? 'rgba(99,102,241,0.1)' : 'transparent', fontSize: 11, color: filter === f.v ? '#818cf8' : ADMIN_COLORS.muted, cursor: 'pointer' }}>
              {f.l}
            </button>
          ))}
        </div>
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {filtered.map(chat => {
            const status = STATUS_CONFIG[chat.status]
            return (
              <button key={chat.id} onClick={() => setSelected(chat)}
                style={{ display: 'flex', gap: 12, padding: '14px 16px', background: chat.status === 'flagged' ? 'rgba(239,68,68,0.03)' : 'none', border: 'none', cursor: 'pointer', textAlign: 'left', borderBottom: `1px solid ${ADMIN_COLORS.border}`, borderLeft: `3px solid ${chat.status === 'flagged' ? '#ef4444' : 'transparent'}` }}>

                {/* Avatars */}
                <div style={{ position: 'relative', width: 46, height: 46, flexShrink: 0 }}>
                  <div style={{ position: 'absolute', top: 0, left: 0, width: 32, height: 32, borderRadius: '50%', background: '#6366f1', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: '#FFFFFF' }}>{chat.buyerAvatar}</span>
                  </div>
                  <div style={{ position: 'absolute', bottom: 0, right: 0, width: 28, height: 28, borderRadius: '50%', background: '#C9A84C', border: `2px solid ${ADMIN_COLORS.bg}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: '#0A0A0A' }}>{chat.sellerAvatar}</span>
                  </div>
                </div>

                {/* Info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: ADMIN_COLORS.text }}>
                      {chat.buyer} ↔ {chat.seller}
                    </span>
                    <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>{chat.lastTime}</span>
                  </div>
                  <p style={{ fontSize: 12, color: '#9A9A9A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: 4 }}>
                    {chat.lastMessage}
                  </p>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 10, fontWeight: 600, color: status.color, background: status.bg, padding: '2px 6px', borderRadius: 20 }}>
                      {status.label}
                    </span>
                    {chat.reports > 0 && (
                      <span style={{ fontSize: 11, color: '#ef4444' }}>⚠️ {chat.reports} reporte(s)</span>
                    )}
                    <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>{chat.messages.length} mensagens</span>
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </AdminLayout>
  )
}
